"""组织范围查询：集团通用（NULL）+ 本级 + 所有上级，对下级自动继承。"""

from __future__ import annotations

from typing import Optional, Set

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.org import OrgUnit


def ancestor_ids(db: Session, org_unit_id: Optional[int]) -> Set[int]:
    ids: Set[int] = set()
    current_id = org_unit_id
    guard = 0
    while current_id and guard < 16:
        node = db.get(OrgUnit, current_id)
        if node is None:
            break
        ids.add(node.id)
        current_id = node.parent_id
        guard += 1
    return ids


def scoped(db: Session, stmt, column, org_unit_id: Optional[int]):
    """给查询加上组织范围条件；org_unit_id 为空表示不限制（管理视角）。"""
    if org_unit_id is None:
        return stmt
    ids = ancestor_ids(db, org_unit_id)
    return stmt.where(or_(column.is_(None), column.in_(ids)))
