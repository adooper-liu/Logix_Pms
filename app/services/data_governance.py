"""数据治理服务：数据域、数据流登记与质量缺口检查。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.data_governance import DataDomain, DataFlow
from app.models.enums import DataDomainType, DataFrequency
from app.models.monitor import KpiDefinition
from app.models.org import OrgUnit
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.data_governance import (
    DataDomainOut,
    DataFlowOut,
    DataGovernanceSummaryOut,
)

DOMAIN_TYPE_LABELS = {
    DataDomainType.CUSTOMER.value: "客户",
    DataDomainType.SUPPLIER.value: "供应商",
    DataDomainType.MATERIAL.value: "物料",
    DataDomainType.PROJECT.value: "项目",
    DataDomainType.ASSET.value: "资产",
    DataDomainType.ORG.value: "组织",
    DataDomainType.LEGAL.value: "法人",
    DataDomainType.PLANT.value: "工厂",
    DataDomainType.COST_CENTER.value: "成本中心",
    DataDomainType.KPI.value: "指标口径",
    DataDomainType.PROCESS.value: "流程版本",
    DataDomainType.OTHER.value: "其他",
}

FREQUENCY_LABELS = {
    DataFrequency.REAL_TIME.value: "实时",
    DataFrequency.DAILY.value: "每日",
    DataFrequency.WEEKLY.value: "每周",
    DataFrequency.MONTHLY.value: "每月",
    DataFrequency.QUARTERLY.value: "每季",
    DataFrequency.AD_HOC.value: "按需",
}


class DataGovernanceError(ValueError):
    """数据治理规则拒绝；API 层转成 400/409。"""


def next_domain_code(db: Session) -> str:
    return _next_code(db, DataDomain.code, "DD")


def next_flow_code(db: Session) -> str:
    return _next_code(db, DataFlow.code, "DF")


def _next_code(db: Session, column, prefix: str) -> str:
    existing = db.scalars(select(column).where(column.like(f"{prefix}-%"))).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{seq + 1:03d}"


def require_domain(db: Session, domain_id: int) -> DataDomain:
    row = db.get(DataDomain, domain_id)
    if row is None:
        raise DataGovernanceError(f"数据域 {domain_id} 不存在")
    return row


def require_flow(db: Session, flow_id: int) -> DataFlow:
    row = db.get(DataFlow, flow_id)
    if row is None:
        raise DataGovernanceError(f"数据流 {flow_id} 不存在")
    return row


def domain_out(db: Session, row: DataDomain) -> DataDomainOut:
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    steward = db.get(User, row.steward_user_id) if row.steward_user_id else None
    org = db.get(OrgUnit, row.org_unit_id) if row.org_unit_id else None
    flow_count = db.scalar(
        select(func.count()).select_from(DataFlow).where(DataFlow.domain_id == row.id)
    )
    return DataDomainOut(
        id=row.id,
        code=row.code,
        name=row.name,
        domain_type=row.domain_type,
        domain_type_label=DOMAIN_TYPE_LABELS.get(row.domain_type, row.domain_type),
        org_unit_id=row.org_unit_id,
        org_unit_name=org.name if org else None,
        owner_user_id=row.owner_user_id,
        owner_name=owner.display_name if owner else None,
        steward_user_id=row.steward_user_id,
        steward_name=steward.display_name if steward else None,
        description=row.description,
        is_active=row.is_active,
        flow_count=int(flow_count or 0),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def flow_out(db: Session, row: DataFlow) -> DataFlowOut:
    domain = db.get(DataDomain, row.domain_id)
    process = db.get(ProcessArch, row.process_id) if row.process_id else None
    kpi = db.get(KpiDefinition, row.kpi_id) if row.kpi_id else None
    return DataFlowOut(
        id=row.id,
        code=row.code,
        name=row.name,
        domain_id=row.domain_id,
        domain_name=domain.name if domain else None,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        kpi_id=row.kpi_id,
        kpi_code=kpi.code if kpi else None,
        kpi_name=kpi.name if kpi else None,
        source_system=row.source_system,
        target_system=row.target_system,
        frequency=row.frequency,
        frequency_label=FREQUENCY_LABELS.get(row.frequency, row.frequency),
        primary_key=row.primary_key,
        field_definitions=row.field_definitions,
        allowed_values=row.allowed_values,
        quality_rule=row.quality_rule,
        purpose=row.purpose,
        retention_period=row.retention_period,
        cross_legal_visibility=row.cross_legal_visibility,
        data_subject_rights=row.data_subject_rights,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_domains(
    db: Session,
    *,
    domain_type: Optional[str] = None,
    active_only: bool = False,
) -> List[DataDomainOut]:
    stmt = select(DataDomain)
    if domain_type is not None:
        stmt = stmt.where(DataDomain.domain_type == domain_type)
    if active_only:
        stmt = stmt.where(DataDomain.is_active.is_(True))
    rows = db.scalars(stmt.order_by(DataDomain.code)).all()
    return [domain_out(db, row) for row in rows]


def list_flows(
    db: Session,
    *,
    domain_id: Optional[int] = None,
    process_id: Optional[int] = None,
    active_only: bool = False,
) -> List[DataFlowOut]:
    stmt = select(DataFlow).options(joinedload(DataFlow.domain))
    if domain_id is not None:
        stmt = stmt.where(DataFlow.domain_id == domain_id)
    if process_id is not None:
        stmt = stmt.where(DataFlow.process_id == process_id)
    if active_only:
        stmt = stmt.where(DataFlow.is_active.is_(True))
    rows = db.scalars(stmt.order_by(DataFlow.code)).all()
    return [flow_out(db, row) for row in rows]


def create_domain(db: Session, data: Dict) -> DataDomain:
    data = dict(data)
    if not data.get("owner_user_id"):
        raise DataGovernanceError("数据域必须指定数据所有者")
    if not data.get("code"):
        data["code"] = next_domain_code(db)
    if db.scalar(select(DataDomain).where(DataDomain.code == data["code"])):
        raise DataGovernanceError(f"数据域编码 {data['code']} 已存在")
    row = DataDomain(**data)
    db.add(row)
    db.flush()
    return row


def update_domain(db: Session, row: DataDomain, data: Dict) -> DataDomain:
    data = dict(data)
    if "code" in data and data["code"] != row.code:
        if db.scalar(
            select(DataDomain).where(DataDomain.code == data["code"], DataDomain.id != row.id)
        ):
            raise DataGovernanceError(f"数据域编码 {data['code']} 已存在")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def delete_domain(db: Session, row: DataDomain) -> None:
    flow_count = db.scalar(
        select(func.count()).select_from(DataFlow).where(DataFlow.domain_id == row.id)
    )
    if flow_count:
        raise DataGovernanceError(f"数据域仍有 {flow_count} 条数据流，请先迁移或删除")
    db.delete(row)
    db.flush()


def _validate_flow(db: Session, data: Dict) -> None:
    if db.get(DataDomain, data["domain_id"]) is None:
        raise DataGovernanceError("数据域不存在")
    if data.get("process_id") is not None and db.get(ProcessArch, data["process_id"]) is None:
        raise DataGovernanceError("关联流程不存在")
    if data.get("kpi_id") is not None and db.get(KpiDefinition, data["kpi_id"]) is None:
        raise DataGovernanceError("关联 KPI 不存在")
    # 来源系统/主键/质量规则不在这里硬拦：它们由治理扫描标记，
    # 允许先登记、后补齐，避免为了通过校验而填假数据。


def create_flow(db: Session, data: Dict) -> DataFlow:
    data = dict(data)
    _validate_flow(db, data)
    if not data.get("code"):
        data["code"] = next_flow_code(db)
    if db.scalar(select(DataFlow).where(DataFlow.code == data["code"])):
        raise DataGovernanceError(f"数据流编码 {data['code']} 已存在")
    row = DataFlow(**data)
    db.add(row)
    db.flush()
    return row


def update_flow(db: Session, row: DataFlow, data: Dict) -> DataFlow:
    data = dict(data)
    if "code" in data and data["code"] != row.code:
        if db.scalar(select(DataFlow).where(DataFlow.code == data["code"], DataFlow.id != row.id)):
            raise DataGovernanceError(f"数据流编码 {data['code']} 已存在")
    merged = {
        key: data.get(key, getattr(row, key)) for key in ("domain_id", "process_id", "kpi_id")
    }
    _validate_flow(db, merged)
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def delete_flow(db: Session, row: DataFlow) -> None:
    db.delete(row)
    db.flush()


def summary(db: Session) -> DataGovernanceSummaryOut:
    domains = list(db.scalars(select(DataDomain).where(DataDomain.is_active.is_(True))).all())
    flows = list(db.scalars(select(DataFlow).where(DataFlow.is_active.is_(True))).all())
    return DataGovernanceSummaryOut(
        domains=len(domains),
        flows=len(flows),
        domains_without_owner=sum(1 for row in domains if row.owner_user_id is None),
        flows_without_quality_rule=sum(1 for row in flows if not (row.quality_rule or "").strip()),
        flows_without_source=sum(1 for row in flows if not (row.source_system or "").strip()),
        flows_without_primary_key=sum(1 for row in flows if not (row.primary_key or "").strip()),
    )


def domain_issues(db: Session) -> List[DataDomain]:
    return list(
        db.scalars(
            select(DataDomain).where(
                DataDomain.is_active.is_(True), DataDomain.owner_user_id.is_(None)
            )
        ).all()
    )


def flow_issues(db: Session) -> List[DataFlow]:
    return list(db.scalars(select(DataFlow).where(DataFlow.is_active.is_(True))).all())
