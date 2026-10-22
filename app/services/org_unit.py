"""组织单元服务：树维护、路径、删除保护。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OrgUnitType
from app.models.org import OrgUnit
from app.models.process_document import ProcessDocument
from app.models.tool_template import ToolTemplate
from app.schemas.org import OrgUnitMeta, OrgUnitOut, OrgUnitTree

TYPE_LABELS: Dict[str, str] = {
    OrgUnitType.GROUP.value: "集团",
    OrgUnitType.COMPANY.value: "公司/分公司",
    OrgUnitType.PLANT.value: "工厂",
    OrgUnitType.DEPARTMENT.value: "部门",
}


class OrgError(ValueError):
    """组织主数据规则拒绝；API 层转成 400/409。"""


def require_org(db: Session, org_unit_id: int) -> OrgUnit:
    org = db.get(OrgUnit, org_unit_id)
    if org is None:
        raise OrgError(f"组织单元 {org_unit_id} 不存在")
    return org


def create_org(db: Session, data: dict) -> OrgUnit:
    parent = None
    if data.get("parent_id") is not None:
        parent = require_org(db, data["parent_id"])
    org = OrgUnit(**data)
    db.add(org)
    db.flush()
    org.path = (parent.path if parent else "/") + f"{org.id}/"
    db.flush()
    return org


def update_org(db: Session, org: OrgUnit, data: dict) -> OrgUnit:
    for field, value in data.items():
        if value is None and field in {"name", "type", "is_active"}:
            continue
        setattr(org, field, value)
    db.flush()
    return org


def delete_org(db: Session, org: OrgUnit) -> None:
    children = (
        db.scalar(select(func.count()).select_from(OrgUnit).where(OrgUnit.parent_id == org.id)) or 0
    )
    documents = (
        db.scalar(
            select(func.count())
            .select_from(ProcessDocument)
            .where(ProcessDocument.org_unit_id == org.id)
        )
        or 0
    )
    templates = (
        db.scalar(
            select(func.count()).select_from(ToolTemplate).where(ToolTemplate.org_unit_id == org.id)
        )
        or 0
    )
    if children or documents or templates:
        raise OrgError(
            f"组织仍有 {children} 个下级、{documents} 份标准文件、{templates} 个模板，"
            "请停用（is_active=false）而不是删除"
        )
    db.delete(org)


def org_out(org: OrgUnit) -> OrgUnitOut:
    return OrgUnitOut(
        id=org.id,
        parent_id=org.parent_id,
        code=org.code,
        name=org.name,
        type=org.type,
        type_label=TYPE_LABELS.get(org.type, org.type),
        path=org.path,
        description=org.description,
        is_active=org.is_active,
        child_count=len(org.children) if org.children is not None else 0,
    )


def build_tree(rows: List[OrgUnit]) -> List[OrgUnitTree]:
    by_id = {row.id: OrgUnitTree(**org_out(row).model_dump(), children=[]) for row in rows}
    roots: List[OrgUnitTree] = []
    for row in rows:
        node = by_id[row.id]
        parent = by_id.get(row.parent_id) if row.parent_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


def meta() -> OrgUnitMeta:
    return OrgUnitMeta(type_labels=TYPE_LABELS)


def resolve_scope(org: Optional[OrgUnit]) -> dict:
    """输出用的范围字段：集团通用或具体组织。"""
    return {
        "org_unit_id": org.id if org else None,
        "scope_org_code": org.code if org else None,
        "scope_org_name": org.name if org else None,
        "scope_label": org.name if org else "集团通用",
    }
