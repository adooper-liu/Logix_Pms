"""岗位主数据服务：组织归属、引用保护。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.org import Position
from app.models.process import ProcessNode
from app.models.user import User
from app.schemas.position import PositionCreate, PositionOut, PositionUpdate
from app.services import org_unit as org_service


class PositionError(ValueError):
    """岗位主数据规则拒绝；API 层转成 400/409。"""


def require_position(db: Session, position_id: int) -> Position:
    row = db.get(Position, position_id)
    if row is None:
        raise PositionError(f"岗位 {position_id} 不存在")
    return row


def list_positions(
    db: Session,
    *,
    active_only: bool = True,
    org_unit_id: Optional[int] = None,
    keyword: Optional[str] = None,
) -> List[Position]:
    stmt = select(Position).options(joinedload(Position.org_unit)).order_by(Position.code)
    if active_only:
        stmt = stmt.where(Position.is_active.is_(True))
    if org_unit_id is not None:
        stmt = stmt.where(Position.org_unit_id == org_unit_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Position.name.like(like), Position.code.like(like)))
    return list(db.scalars(stmt).all())


def position_out(row: Position) -> PositionOut:
    return PositionOut.model_validate(row)


def _validate_org(db: Session, org_unit_id: Optional[int]) -> None:
    if org_unit_id is None:
        return
    try:
        org_service.require_org(db, org_unit_id)
    except org_service.OrgError as exc:
        raise PositionError(str(exc)) from exc


def create_position(db: Session, payload: PositionCreate) -> Position:
    if db.scalar(select(Position).where(Position.code == payload.code)):
        raise PositionError(f"岗位编码 {payload.code} 已存在")
    _validate_org(db, payload.org_unit_id)
    row = Position(
        code=payload.code,
        name=payload.name,
        org_unit_id=payload.org_unit_id,
        description=payload.description,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    return row


def update_position(db: Session, row: Position, payload: PositionUpdate) -> Position:
    data: Dict = payload.model_dump(exclude_unset=True)
    if "org_unit_id" in data:
        _validate_org(db, data["org_unit_id"])
    for key, value in data.items():
        if value is None and key in {"name", "org_unit_id"}:
            continue
        setattr(row, key, value)
    db.flush()
    return row


def delete_position(db: Session, row: Position) -> None:
    users = db.scalar(select(func.count()).select_from(User).where(User.position_id == row.id)) or 0
    nodes = (
        db.scalar(
            select(func.count())
            .select_from(ProcessNode)
            .where(ProcessNode.owner_position_id == row.id)
        )
        or 0
    )
    if users or nodes:
        raise PositionError(
            f"岗位仍被 {users} 个用户、{nodes} 个流程节点引用，请停用（is_active=false）而不是删除"
        )
    db.delete(row)
