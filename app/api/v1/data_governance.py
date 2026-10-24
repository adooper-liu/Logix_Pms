"""数据治理 API：数据域、数据流与质量缺口概览。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.enums import DataDomainType
from app.models.user import User
from app.schemas.common import DeleteResult, as_columns
from app.schemas.data_governance import (
    DataDomainCreate,
    DataDomainOut,
    DataDomainUpdate,
    DataFlowCreate,
    DataFlowOut,
    DataFlowUpdate,
    DataGovernanceMetaOut,
    DataGovernanceSummaryOut,
)
from app.services import audit as audit_service
from app.services import data_governance as data_service

router = APIRouter(prefix="/data-governance", tags=["数据治理"])


def _require_domain(db: DbSession, domain_id: int):
    try:
        return data_service.require_domain(db, domain_id)
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_flow(db: DbSession, flow_id: int):
    try:
        return data_service.require_flow(db, flow_id)
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _resolve_person(
    db: DbSession, user_id: Optional[int], name: Optional[str], label: str
) -> Optional[int]:
    """把 owner/steward 解析成用户外键；姓名有歧义时 fail closed。"""
    if user_id is not None:
        if db.get(User, user_id) is None:
            raise HTTPException(status_code=400, detail=f"{label}指向的用户不存在")
        return user_id
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    matches = db.scalars(select(User).where(User.display_name == cleaned)).all()
    if len(matches) == 1:
        return matches[0].id
    raise HTTPException(
        status_code=400,
        detail=f"{label}「{cleaned}」无法唯一匹配账号，请直接从人员列表选择",
    )


@router.get("/meta", response_model=DataGovernanceMetaOut, summary="数据域类型与频率标签")
def data_meta():
    return DataGovernanceMetaOut(
        domain_type_labels=data_service.DOMAIN_TYPE_LABELS,
        frequency_labels=data_service.FREQUENCY_LABELS,
    )


@router.get("/summary", response_model=DataGovernanceSummaryOut, summary="数据治理缺口概览")
def data_summary(db: DbSession, user: CurrentUser):
    return data_service.summary(db)


@router.get("/domains", response_model=List[DataDomainOut], summary="数据域清单")
def list_domains(
    db: DbSession,
    user: CurrentUser,
    domain_type: Optional[DataDomainType] = None,
    active_only: bool = False,
):
    return data_service.list_domains(
        db,
        domain_type=domain_type.value if domain_type else None,
        active_only=active_only,
    )


@router.post(
    "/domains",
    response_model=DataDomainOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建数据域",
)
def create_domain(payload: DataDomainCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump())
    data["owner_user_id"] = _resolve_person(db, payload.owner_user_id, payload.owner, "数据所有者")
    data["steward_user_id"] = _resolve_person(
        db, payload.steward_user_id, payload.steward, "数据管家"
    )
    data.pop("owner", None)
    data.pop("steward", None)
    try:
        row = data_service.create_domain(db, data)
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "CREATE", "data_domain", row.id, f"新增数据域 {row.code} {row.name}"
    )
    db.commit()
    db.refresh(row)
    return data_service.domain_out(db, row)


@router.patch("/domains/{domain_id}", response_model=DataDomainOut, summary="修改数据域")
def update_domain(
    domain_id: int,
    payload: DataDomainUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = _require_domain(db, domain_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    if "owner_user_id" in data or "owner" in data:
        data["owner_user_id"] = _resolve_person(
            db, data.get("owner_user_id"), data.get("owner"), "数据所有者"
        )
    if "steward_user_id" in data or "steward" in data:
        data["steward_user_id"] = _resolve_person(
            db, data.get("steward_user_id"), data.get("steward"), "数据管家"
        )
    data.pop("owner", None)
    data.pop("steward", None)
    try:
        data_service.update_domain(db, row, data)
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(db, user, "UPDATE", "data_domain", row.id, f"修改数据域 {row.code}")
    db.commit()
    db.refresh(row)
    return data_service.domain_out(db, row)


@router.delete(
    "/domains/{domain_id}", response_model=DeleteResult, summary="删除数据域（无数据流时）"
)
def delete_domain(domain_id: int, db: DbSession, user: ManagerUser):
    row = _require_domain(db, domain_id)
    try:
        data_service.delete_domain(db, row)
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.record(db, user, "DELETE", "data_domain", row.id, f"删除数据域 {row.code}")
    db.commit()
    return DeleteResult(deleted=1)


@router.get("/flows", response_model=List[DataFlowOut], summary="数据流清单")
def list_flows(
    db: DbSession,
    user: CurrentUser,
    domain_id: Optional[int] = None,
    process_id: Optional[int] = None,
    active_only: bool = False,
):
    return data_service.list_flows(
        db, domain_id=domain_id, process_id=process_id, active_only=active_only
    )


@router.post(
    "/flows",
    response_model=DataFlowOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建数据流",
)
def create_flow(payload: DataFlowCreate, db: DbSession, user: ManagerUser):
    try:
        row = data_service.create_flow(db, as_columns(payload.model_dump()))
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "CREATE", "data_flow", row.id, f"新增数据流 {row.code} {row.name}"
    )
    db.commit()
    db.refresh(row)
    return data_service.flow_out(db, row)


@router.patch("/flows/{flow_id}", response_model=DataFlowOut, summary="修改数据流")
def update_flow(flow_id: int, payload: DataFlowUpdate, db: DbSession, user: ManagerUser):
    row = _require_flow(db, flow_id)
    try:
        data_service.update_flow(db, row, as_columns(payload.model_dump(exclude_unset=True)))
    except data_service.DataGovernanceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(db, user, "UPDATE", "data_flow", row.id, f"修改数据流 {row.code}")
    db.commit()
    db.refresh(row)
    return data_service.flow_out(db, row)


@router.delete("/flows/{flow_id}", response_model=DeleteResult, summary="删除数据流")
def delete_flow(flow_id: int, db: DbSession, user: ManagerUser):
    row = _require_flow(db, flow_id)
    data_service.delete_flow(db, row)
    audit_service.record(db, user, "DELETE", "data_flow", row.id, f"删除数据流 {row.code}")
    db.commit()
    return DeleteResult(deleted=1)
