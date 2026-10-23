"""岗位主数据 API：组织内的职责口径，供流程活动与人员引用。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models.org import Position
from app.schemas.common import DeleteResult
from app.schemas.position import PositionCreate, PositionOut, PositionUpdate
from app.services import audit as audit_service
from app.services import position as position_service

router = APIRouter(prefix="/positions", tags=["岗位主数据"])


@router.get("", response_model=List[PositionOut], summary="岗位清单")
def list_positions(
    db: DbSession,
    user: CurrentUser,
    active_only: bool = True,
    org_unit_id: Optional[int] = None,
    keyword: Optional[str] = None,
):
    rows = position_service.list_positions(
        db, active_only=active_only, org_unit_id=org_unit_id, keyword=keyword
    )
    return [position_service.position_out(row) for row in rows]


@router.post(
    "",
    response_model=PositionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建岗位（管理员）",
)
def create_position(payload: PositionCreate, db: DbSession, user: AdminUser):
    try:
        row = position_service.create_position(db, payload)
    except position_service.PositionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "position",
        row.id,
        f"新建岗位 {row.code} {row.name}",
    )
    db.commit()
    db.refresh(row)
    return position_service.position_out(row)


@router.patch("/{position_id}", response_model=PositionOut, summary="修改岗位（管理员）")
def update_position(position_id: int, payload: PositionUpdate, db: DbSession, user: AdminUser):
    row = db.get(Position, position_id)
    if row is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    try:
        row = position_service.update_position(db, row, payload)
    except position_service.PositionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "position",
        row.id,
        f"更新岗位 {row.code}",
    )
    db.commit()
    db.refresh(row)
    return position_service.position_out(row)


@router.delete(
    "/{position_id}",
    response_model=DeleteResult,
    summary="删除岗位（无用户/流程节点引用时，管理员）",
)
def delete_position(position_id: int, db: DbSession, user: AdminUser):
    row = db.get(Position, position_id)
    if row is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    try:
        position_service.delete_position(db, row)
    except position_service.PositionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    code = row.code
    audit_service.record(db, user, "DELETE", "position", position_id, f"删除岗位 {code}")
    db.commit()
    return DeleteResult(deleted=1)
