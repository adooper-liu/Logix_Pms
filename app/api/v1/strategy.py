"""战略目标 API：目标维护、流程/KPI 承接、按流程或 KPI 反查。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    apply_owner_update,
    resolve_owner,
)
from app.models.enums import StrategyStatus
from app.schemas.common import DeleteResult, as_columns
from app.schemas.strategy import (
    ObjectiveLinkCreate,
    ObjectiveLinkOut,
    StrategyMetaOut,
    StrategyObjectiveCreate,
    StrategyObjectiveOut,
    StrategyObjectiveUpdate,
    StrategySummaryOut,
)
from app.services import audit as audit_service
from app.services import strategy as strategy_service

router = APIRouter(prefix="/strategy", tags=["战略目标"])


def _require_objective(db: DbSession, objective_id: int):
    try:
        return strategy_service.require_objective(db, objective_id)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/meta", response_model=StrategyMetaOut, summary="战略目标枚举中文标签")
def strategy_meta():
    return StrategyMetaOut(
        period_labels=strategy_service.PERIOD_LABELS,
        status_labels=strategy_service.STATUS_LABELS,
    )


@router.get("/summary", response_model=StrategySummaryOut, summary="年度目标承接概览")
def summary(db: DbSession, user: CurrentUser, year: Optional[int] = None):
    return strategy_service.summary(db, year or date.today().year)


@router.get(
    "/objectives",
    response_model=List[StrategyObjectiveOut],
    summary="战略目标清单",
)
def list_objectives(
    db: DbSession,
    user: CurrentUser,
    year: Optional[int] = None,
    status_: Optional[StrategyStatus] = Query(default=None, alias="status"),
    owner_user_id: Optional[int] = None,
):
    return strategy_service.list_objectives(
        db,
        year=year,
        status=status_.value if status_ else None,
        owner_user_id=owner_user_id,
    )


@router.get(
    "/objectives/{objective_id}",
    response_model=StrategyObjectiveOut,
    summary="战略目标详情（含承接关系）",
)
def get_objective(objective_id: int, db: DbSession, user: CurrentUser):
    row = _require_objective(db, objective_id)
    return strategy_service.objective_out(db, row)


@router.post(
    "/objectives",
    response_model=StrategyObjectiveOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增战略目标",
)
def create_objective(payload: StrategyObjectiveCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump())
    data["owner_user_id"], data["owner"] = resolve_owner(db, payload.owner_user_id, payload.owner)
    try:
        row = strategy_service.create_objective(db, data)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "strategy_objective",
        row.id,
        f"新增战略目标 {row.code} {row.name}（{row.year}）",
    )
    db.commit()
    db.refresh(row)
    return strategy_service.objective_out(db, row)


@router.patch(
    "/objectives/{objective_id}",
    response_model=StrategyObjectiveOut,
    summary="修改战略目标",
)
def update_objective(
    objective_id: int,
    payload: StrategyObjectiveUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = _require_objective(db, objective_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    apply_owner_update(db, data, row.owner)
    try:
        strategy_service.update_objective(db, row, data)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "strategy_objective",
        row.id,
        f"修改战略目标 {row.code}（{', '.join(sorted(data))}）",
    )
    db.commit()
    db.refresh(row)
    return strategy_service.objective_out(db, row)


@router.delete(
    "/objectives/{objective_id}",
    response_model=DeleteResult,
    summary="删除战略目标（承接关系一并删除）",
)
def delete_objective(objective_id: int, db: DbSession, user: ManagerUser):
    row = _require_objective(db, objective_id)
    audit_service.record(
        db, user, "DELETE", "strategy_objective", row.id, f"删除战略目标 {row.code}"
    )
    db.delete(row)
    db.commit()
    return DeleteResult(deleted=1)


@router.post(
    "/objectives/{objective_id}/links",
    response_model=ObjectiveLinkOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增承接关系（目标 → 流程 → 可选 KPI）",
)
def add_link(
    objective_id: int,
    payload: ObjectiveLinkCreate,
    db: DbSession,
    user: ManagerUser,
):
    row = _require_objective(db, objective_id)
    try:
        link = strategy_service.add_link(
            db,
            row,
            process_id=payload.process_id,
            kpi_id=payload.kpi_id,
            note=payload.note,
        )
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "strategy_objective",
        row.id,
        f"目标 {row.code} 承接流程 {payload.process_id}"
        + (f" / KPI {payload.kpi_id}" if payload.kpi_id else ""),
    )
    db.commit()
    db.refresh(link)
    return strategy_service.link_out(db, link)


@router.delete(
    "/objectives/{objective_id}/links/{link_id}",
    response_model=DeleteResult,
    summary="删除承接关系",
)
def remove_link(objective_id: int, link_id: int, db: DbSession, user: ManagerUser):
    row = _require_objective(db, objective_id)
    try:
        strategy_service.remove_link(db, row, link_id)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "strategy_objective",
        row.id,
        f"目标 {row.code} 移除承接关系 {link_id}",
    )
    db.commit()
    return DeleteResult(deleted=1)


@router.get(
    "/processes/{process_id}/objectives",
    response_model=List[StrategyObjectiveOut],
    summary="按流程反查战略目标（含上级继承）",
)
def objectives_for_process(process_id: int, db: DbSession, user: CurrentUser):
    try:
        return strategy_service.objectives_for_process(db, process_id)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/kpis/{kpi_id}/objectives",
    response_model=List[StrategyObjectiveOut],
    summary="按 KPI 反查战略目标",
)
def objectives_for_kpi(kpi_id: int, db: DbSession, user: CurrentUser):
    try:
        return strategy_service.objectives_for_kpi(db, kpi_id)
    except strategy_service.StrategyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
