"""业务数据的组织可见范围。

ADMIN / MANAGER 看全部。其他角色看集团通用（org_unit_id 为空）以及自己所在组织
的下级。流程架构本身仍是全公司一张图，不在这里裁剪。
"""

from __future__ import annotations

from typing import Optional, Set

from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.enums import Role
from app.models.org import OrgUnit
from app.models.user import User

_OPEN_ROLES = {Role.ADMIN.value, Role.MANAGER.value}


def unrestricted(user: User) -> bool:
    return user.role in _OPEN_ROLES


def subtree_ids(db: Session, org_unit_id: Optional[int]) -> Set[int]:
    if org_unit_id is None:
        return set()
    node = db.get(OrgUnit, org_unit_id)
    if node is None or not node.path:
        return {org_unit_id}
    rows = db.scalars(select(OrgUnit.id).where(OrgUnit.path.startswith(node.path))).all()
    return set(rows) or {org_unit_id}


def restrict(stmt, db: Session, user: User, column):
    if unrestricted(user):
        return stmt
    ids = subtree_ids(db, user.org_unit_id)
    if not ids:
        return stmt.where(column.is_(None))
    return stmt.where(or_(column.is_(None), column.in_(ids)))


def ensure_visible(db: Session, user: User, org_unit_id: Optional[int]) -> None:
    if unrestricted(user) or org_unit_id is None:
        return
    if org_unit_id not in subtree_ids(db, user.org_unit_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="对象不存在")
