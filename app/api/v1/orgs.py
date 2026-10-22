"""组织单元 API：集团 → 公司 → 工厂 → 部门。

组织编码属于主数据，写操作只允许系统管理员；业务用户只读。
标准文件与模板通过 `org_unit_id` 标范围，NULL 表示集团通用。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import AdminUser, DbSession
from app.models.enums import OrgUnitType
from app.models.org import OrgUnit
from app.schemas.common import DeleteResult, as_columns
from app.schemas.org import (
    OrgUnitCreate,
    OrgUnitMeta,
    OrgUnitOut,
    OrgUnitTree,
    OrgUnitUpdate,
)
from app.services import audit as audit_service
from app.services import org_unit as org_service

router = APIRouter(prefix="/org-units", tags=["组织单元"])


@router.get("/meta", response_model=OrgUnitMeta, summary="组织类型标签")
def meta():
    return org_service.meta()


@router.get("", response_model=List[OrgUnitOut], summary="组织清单（扁平）")
def list_orgs(
    db: DbSession,
    type: Optional[OrgUnitType] = None,
    parent_id: Optional[int] = None,
    keyword: Optional[str] = None,
    active_only: bool = True,
):
    stmt = (
        select(OrgUnit).options(selectinload(OrgUnit.children)).order_by(OrgUnit.path, OrgUnit.code)
    )
    if type is not None:
        stmt = stmt.where(OrgUnit.type == type.value)
    if parent_id is not None:
        stmt = stmt.where(OrgUnit.parent_id == parent_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(OrgUnit.name.like(like), OrgUnit.code.like(like)))
    if active_only:
        stmt = stmt.where(OrgUnit.is_active.is_(True))
    return [org_service.org_out(row) for row in db.scalars(stmt).all()]


@router.get("/tree", response_model=List[OrgUnitTree], summary="组织树")
def org_tree(db: DbSession, active_only: bool = True):
    stmt = select(OrgUnit).options(selectinload(OrgUnit.children)).order_by(OrgUnit.code)
    if active_only:
        stmt = stmt.where(OrgUnit.is_active.is_(True))
    return org_service.build_tree(list(db.scalars(stmt).all()))


@router.post(
    "",
    response_model=OrgUnitOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建组织（管理员）",
)
def create_org(payload: OrgUnitCreate, db: DbSession, user: AdminUser):
    if db.scalar(select(OrgUnit).where(OrgUnit.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"组织编码 {payload.code} 已存在")
    data = as_columns(payload.model_dump())
    try:
        org = org_service.create_org(db, data)
    except org_service.OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "org_unit",
        org.id,
        f"新建组织 {org.code} {org.name}（{org.type}）",
    )
    db.commit()
    db.refresh(org)
    return org_service.org_out(org)


@router.patch("/{org_id}", response_model=OrgUnitOut, summary="修改组织（管理员）")
def update_org(org_id: int, payload: OrgUnitUpdate, db: DbSession, user: AdminUser):
    org = db.get(OrgUnit, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="组织不存在")
    data = as_columns(payload.model_dump(exclude_unset=True))
    try:
        org = org_service.update_org(db, org, data)
    except org_service.OrgError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "org_unit",
        org.id,
        f"更新组织 {org.code}：{', '.join(sorted(data.keys())) or '（无变更）'}",
    )
    db.commit()
    db.refresh(org)
    return org_service.org_out(org)


@router.delete(
    "/{org_id}", response_model=DeleteResult, summary="删除组织（无下级/引用时，管理员）"
)
def delete_org(org_id: int, db: DbSession, user: AdminUser):
    org = db.get(OrgUnit, org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="组织不存在")
    try:
        org_service.delete_org(db, org)
    except org_service.OrgError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    code = org.code
    audit_service.record(db, user, "DELETE", "org_unit", org_id, f"删除组织 {code}")
    db.commit()
    return DeleteResult(deleted=1)
