"""战略目标服务：目标维护、流程/KPI 承接与反查。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.enums import StrategyPeriod, StrategyStatus
from app.models.monitor import KpiDefinition
from app.models.process import ProcessArch
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.user import User
from app.schemas.strategy import (
    ObjectiveLinkOut,
    StrategyObjectiveOut,
    StrategySummaryOut,
)
from app.services import process_scope

PERIOD_LABELS = {
    StrategyPeriod.ANNUAL.value: "年度",
    StrategyPeriod.H1.value: "上半年",
    StrategyPeriod.H2.value: "下半年",
    StrategyPeriod.Q1.value: "一季度",
    StrategyPeriod.Q2.value: "二季度",
    StrategyPeriod.Q3.value: "三季度",
    StrategyPeriod.Q4.value: "四季度",
}

STATUS_LABELS = {
    StrategyStatus.ACTIVE.value: "进行中",
    StrategyStatus.ARCHIVED.value: "已归档",
}


class StrategyError(ValueError):
    """战略目标规则拒绝；API 层转成 400/409。"""


def next_code(db: Session, year: int) -> str:
    prefix = f"OBJ-{year}-"
    existing = db.scalars(
        select(StrategyObjective.code).where(StrategyObjective.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:02d}"


def require_objective(db: Session, objective_id: int) -> StrategyObjective:
    row = db.get(StrategyObjective, objective_id)
    if row is None:
        raise StrategyError(f"战略目标 {objective_id} 不存在")
    return row


def create_objective(db: Session, data: Dict) -> StrategyObjective:
    data = dict(data)
    if not data.get("code"):
        data["code"] = next_code(db, data["year"])
    if db.scalar(select(StrategyObjective).where(StrategyObjective.code == data["code"])):
        raise StrategyError(f"目标编码 {data['code']} 已存在")
    row = StrategyObjective(**data)
    db.add(row)
    db.flush()
    return row


def update_objective(db: Session, row: StrategyObjective, data: Dict) -> StrategyObjective:
    data = dict(data)
    if "code" in data and data["code"] != row.code:
        if db.scalar(
            select(StrategyObjective).where(
                StrategyObjective.code == data["code"],
                StrategyObjective.id != row.id,
            )
        ):
            raise StrategyError(f"目标编码 {data['code']} 已存在")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def _validate_link(db: Session, process_id: int, kpi_id: Optional[int]) -> None:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise StrategyError(f"流程 {process_id} 不存在")
    if kpi_id is None:
        return
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise StrategyError(f"KPI {kpi_id} 不存在")
    if kpi.process_id is None:
        return
    # KPI 必须挂在所选流程或其下级，避免目标—流程—指标错位
    if process_id not in process_scope.ancestor_ids(db, kpi.process_id):
        raise StrategyError("所选 KPI 不属于该流程（或其下级流程）")


def add_link(
    db: Session,
    objective: StrategyObjective,
    *,
    process_id: int,
    kpi_id: Optional[int],
    note: Optional[str],
) -> ObjectiveProcessLink:
    _validate_link(db, process_id, kpi_id)
    stmt = select(ObjectiveProcessLink).where(
        ObjectiveProcessLink.objective_id == objective.id,
        ObjectiveProcessLink.process_id == process_id,
    )
    if kpi_id is None:
        stmt = stmt.where(ObjectiveProcessLink.kpi_id.is_(None))
    else:
        stmt = stmt.where(ObjectiveProcessLink.kpi_id == kpi_id)
    if db.scalar(stmt):
        raise StrategyError("该承接关系已存在")
    link = ObjectiveProcessLink(
        objective_id=objective.id,
        process_id=process_id,
        kpi_id=kpi_id,
        note=note,
    )
    db.add(link)
    db.flush()
    return link


def remove_link(db: Session, objective: StrategyObjective, link_id: int) -> None:
    link = db.get(ObjectiveProcessLink, link_id)
    if link is None or link.objective_id != objective.id:
        raise StrategyError(f"承接关系 {link_id} 不存在")
    db.delete(link)
    db.flush()


def link_out(db: Session, link: ObjectiveProcessLink) -> ObjectiveLinkOut:
    process = db.get(ProcessArch, link.process_id)
    kpi = db.get(KpiDefinition, link.kpi_id) if link.kpi_id else None
    return ObjectiveLinkOut(
        id=link.id,
        process_id=link.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        process_level=process.level if process else None,
        kpi_id=link.kpi_id,
        kpi_code=kpi.code if kpi else None,
        kpi_name=kpi.name if kpi else None,
        note=link.note,
    )


def objective_out(db: Session, row: StrategyObjective) -> StrategyObjectiveOut:
    links = [link_out(db, link) for link in row.links]
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    return StrategyObjectiveOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        year=row.year,
        period=row.period,
        period_label=PERIOD_LABELS.get(row.period, row.period),
        baseline_value=row.baseline_value,
        target_value=row.target_value,
        unit=row.unit,
        source_document=row.source_document,
        owner=row.owner or (owner.display_name if owner else None),
        owner_user_id=row.owner_user_id,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        links=links,
        process_count=len({link.process_id for link in links}),
        kpi_count=len({link.kpi_id for link in links if link.kpi_id is not None}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _base_query():
    return select(StrategyObjective).options(
        selectinload(StrategyObjective.links).joinedload(ObjectiveProcessLink.process),
        selectinload(StrategyObjective.links).joinedload(ObjectiveProcessLink.kpi),
    )


def list_objectives(
    db: Session,
    *,
    year: Optional[int] = None,
    status: Optional[str] = None,
    owner_user_id: Optional[int] = None,
) -> List[StrategyObjectiveOut]:
    stmt = _base_query()
    if year is not None:
        stmt = stmt.where(StrategyObjective.year == year)
    if status is not None:
        stmt = stmt.where(StrategyObjective.status == status)
    if owner_user_id is not None:
        stmt = stmt.where(StrategyObjective.owner_user_id == owner_user_id)
    rows = db.scalars(stmt.order_by(StrategyObjective.year.desc(), StrategyObjective.code)).all()
    return [objective_out(db, row) for row in rows]


def objectives_for_process(db: Session, process_id: int) -> List[StrategyObjectiveOut]:
    if db.get(ProcessArch, process_id) is None:
        raise StrategyError(f"流程 {process_id} 不存在")
    ancestors = process_scope.ancestor_ids(db, process_id)
    objective_ids = set(
        db.scalars(
            select(ObjectiveProcessLink.objective_id).where(
                ObjectiveProcessLink.process_id.in_(ancestors)
            )
        ).all()
    )
    if not objective_ids:
        return []
    rows = db.scalars(_base_query().where(StrategyObjective.id.in_(objective_ids))).all()
    return [objective_out(db, row) for row in rows]


def objectives_for_kpi(db: Session, kpi_id: int) -> List[StrategyObjectiveOut]:
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise StrategyError(f"KPI {kpi_id} 不存在")
    conditions = [ObjectiveProcessLink.kpi_id == kpi_id]
    if kpi.process_id is not None:
        ancestors = process_scope.ancestor_ids(db, kpi.process_id)
        conditions.append(
            (ObjectiveProcessLink.kpi_id.is_(None))
            & (ObjectiveProcessLink.process_id.in_(ancestors))
        )
    objective_ids = set(
        db.scalars(select(ObjectiveProcessLink.objective_id).where(or_(*conditions))).all()
    )
    if not objective_ids:
        return []
    rows = db.scalars(_base_query().where(StrategyObjective.id.in_(objective_ids))).all()
    return [objective_out(db, row) for row in rows]


def summary(db: Session, year: int) -> StrategySummaryOut:
    rows = db.scalars(_base_query().where(StrategyObjective.year == year)).all()
    active = sum(1 for row in rows if row.status == StrategyStatus.ACTIVE.value)
    linked = sum(1 for row in rows if row.links)
    kpi_links = sum(1 for row in rows for link in row.links if link.kpi_id is not None)
    return StrategySummaryOut(
        year=year,
        objective_count=len(rows),
        active_count=active,
        archived_count=len(rows) - active,
        linked_count=linked,
        unlinked_count=len(rows) - linked,
        kpi_link_count=kpi_links,
    )
