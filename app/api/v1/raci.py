"""治理角色与 RACI API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.raci import RaciAssignment
from app.schemas.common import DeleteResult, as_columns
from app.schemas.raci import (
    GovernanceMemberCreate,
    GovernanceMemberOut,
    GovernanceRoleCreate,
    GovernanceRoleOut,
    GovernanceRoleUpdate,
    RaciCreate,
    RaciMetaOut,
    RaciOut,
    RaciProcessOut,
)
from app.services import audit as audit_service
from app.services import raci as raci_service

router = APIRouter(prefix="/governance", tags=["治理角色与 RACI"])


def _require_role(db: DbSession, role_id: int):
    try:
        return raci_service.require_role(db, role_id)
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _require_raci(db: DbSession, raci_id: int) -> RaciAssignment:
    row = db.get(RaciAssignment, raci_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"RACI 记录 {raci_id} 不存在")
    return row


@router.get("/meta", response_model=RaciMetaOut, summary="治理角色与 RACI 中文标签")
def raci_meta():
    return RaciMetaOut(
        role_type_labels=raci_service.ROLE_TYPE_LABELS,
        raci_labels=raci_service.RACI_LABELS,
    )


@router.get("/roles", response_model=List[GovernanceRoleOut], summary="治理角色清单")
def list_roles(
    db: DbSession,
    user: CurrentUser,
    active_only: bool = False,
    role_type: Optional[str] = None,
):
    return raci_service.list_roles(db, active_only=active_only, role_type=role_type)


@router.post(
    "/roles",
    response_model=GovernanceRoleOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建治理角色",
)
def create_role(payload: GovernanceRoleCreate, db: DbSession, user: ManagerUser):
    try:
        row = raci_service.create_role(db, as_columns(payload.model_dump()))
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "CREATE", "governance_role", row.id, f"新增治理角色 {row.code} {row.name}"
    )
    db.commit()
    db.refresh(row)
    return raci_service.role_out(db, row)


@router.patch("/roles/{role_id}", response_model=GovernanceRoleOut, summary="修改治理角色")
def update_role(
    role_id: int,
    payload: GovernanceRoleUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = _require_role(db, role_id)
    try:
        raci_service.update_role(db, row, as_columns(payload.model_dump(exclude_unset=True)))
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(db, user, "UPDATE", "governance_role", row.id, f"修改治理角色 {row.code}")
    db.commit()
    db.refresh(row)
    return raci_service.role_out(db, row)


@router.delete(
    "/roles/{role_id}", response_model=DeleteResult, summary="删除治理角色（未被 RACI 使用时）"
)
def delete_role(role_id: int, db: DbSession, user: ManagerUser):
    row = _require_role(db, role_id)
    try:
        raci_service.delete_role(db, row)
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.record(db, user, "DELETE", "governance_role", row.id, f"删除治理角色 {row.code}")
    db.commit()
    return DeleteResult(deleted=1)


@router.post(
    "/roles/{role_id}/members",
    response_model=GovernanceMemberOut,
    status_code=status.HTTP_201_CREATED,
    summary="添加角色成员",
)
def add_member(
    role_id: int,
    payload: GovernanceMemberCreate,
    db: DbSession,
    user: ManagerUser,
):
    role = _require_role(db, role_id)
    try:
        member = raci_service.add_member(db, role, payload.user_id, is_primary=payload.is_primary)
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "governance_role",
        role.id,
        f"角色 {role.code} 添加成员用户 {payload.user_id}",
    )
    db.commit()
    db.refresh(member)
    return raci_service.member_out(member)


@router.delete(
    "/roles/{role_id}/members/{member_id}",
    response_model=DeleteResult,
    summary="移除角色成员",
)
def remove_member(role_id: int, member_id: int, db: DbSession, user: ManagerUser):
    role = _require_role(db, role_id)
    try:
        raci_service.remove_member(db, role, member_id)
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "governance_role",
        role.id,
        f"角色 {role.code} 移除成员 {member_id}",
    )
    db.commit()
    return DeleteResult(deleted=1)


@router.get(
    "/raci",
    response_model=RaciProcessOut,
    summary="流程权责矩阵（按事项分组）",
)
def process_raci(db: DbSession, user: CurrentUser, process_id: int):
    try:
        return raci_service.process_raci(db, process_id)
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/raci",
    response_model=RaciOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增或更新一条 RACI（同一事项唯一 A）",
)
def upsert_raci(payload: RaciCreate, db: DbSession, user: ManagerUser):
    try:
        row = raci_service.upsert_raci(db, as_columns(payload.model_dump()))
    except raci_service.RaciError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process",
        payload.process_id,
        f"RACI：{payload.matter} / 角色 {payload.role_id} = {payload.raci}",
    )
    db.commit()
    db.refresh(row)
    return raci_service.raci_out(db, row)


@router.delete("/raci/{raci_id}", response_model=DeleteResult, summary="删除 RACI 记录")
def delete_raci(raci_id: int, db: DbSession, user: ManagerUser):
    row = _require_raci(db, raci_id)
    process_id = row.process_id
    matter = row.matter
    raci_service.remove_raci(db, row)
    audit_service.record(db, user, "UPDATE", "process", process_id, f"删除 RACI：{matter}")
    db.commit()
    return DeleteResult(deleted=1)
