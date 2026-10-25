"""复制资产包：创建、校验与资产解析。"""

from __future__ import annotations

from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models.knowledge import KnowledgeItem
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.replication import ReplicationPack
from app.models.tool_template import ToolTemplate
from app.models.user import User
from app.schemas.replication import ReplicationAssetOut, ReplicationPackOut

STATUS_LABELS: Dict[str, str] = {
    "DRAFT": "草稿",
    "PUBLISHED": "已发布",
    "REJECTED": "已拒绝",
}


class ReplicationError(ValueError):
    pass


def _assets(db: Session, ids: List[int], model, title_field: str) -> List[ReplicationAssetOut]:
    if not ids:
        return []
    rows = db.scalars(select(model).where(model.id.in_(ids))).all()
    result = []
    for row in rows:
        result.append(
            ReplicationAssetOut(
                id=row.id,
                code=getattr(row, "code", None),
                title=getattr(row, title_field),
            )
        )
    return result


def pack_out(db: Session, row: ReplicationPack) -> ReplicationPackOut:
    project = db.get(Project, row.source_project_id) if row.source_project_id else None
    owner = db.get(User, row.owner_user_id) if row.owner_user_id else None
    return ReplicationPackOut(
        id=row.id,
        source_project_id=row.source_project_id,
        source_project_code=project.code if project else None,
        title=row.title,
        conditions=row.conditions,
        benefit_evidence=row.benefit_evidence,
        failure_notes=row.failure_notes,
        rejection_reason=row.rejection_reason,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        owner_user_id=row.owner_user_id,
        owner=owner.display_name if owner else None,
        knowledge=_assets(db, list(row.knowledge_ids or []), KnowledgeItem, "title"),
        documents=_assets(db, list(row.document_ids or []), ProcessDocument, "title"),
        templates=_assets(db, list(row.template_ids or []), ToolTemplate, "name"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _validate_ids(db: Session, ids: List[int], model, label: str) -> None:
    if not ids:
        return
    found = set(db.scalars(select(model.id).where(model.id.in_(ids))).all())
    missing = sorted(set(ids) - found)
    if missing:
        raise ReplicationError(f"{label}不存在：{', '.join(str(v) for v in missing)}")


def validate_pack(db: Session, data: dict) -> None:
    if data.get("source_project_id") is not None:
        if db.get(Project, data["source_project_id"]) is None:
            raise ReplicationError("来源项目不存在")
    _validate_ids(db, data.get("knowledge_ids") or [], KnowledgeItem, "知识条目")
    _validate_ids(db, data.get("document_ids") or [], ProcessDocument, "标准文件")
    _validate_ids(db, data.get("template_ids") or [], ToolTemplate, "工具模板")


def create_pack(db: Session, data: dict, user: User) -> ReplicationPack:
    validate_pack(db, data)
    if not (data.get("conditions") or "").strip():
        raise ReplicationError("复制资产包必须写明适用条件")
    row = ReplicationPack(
        source_project_id=data.get("source_project_id"),
        title=data["title"],
        conditions=data.get("conditions"),
        benefit_evidence=data.get("benefit_evidence"),
        failure_notes=data.get("failure_notes"),
        status="DRAFT",
        owner_user_id=user.id,
        knowledge_ids=data.get("knowledge_ids") or [],
        document_ids=data.get("document_ids") or [],
        template_ids=data.get("template_ids") or [],
    )
    db.add(row)
    db.flush()
    return row


def update_pack(db: Session, row: ReplicationPack, data: dict) -> ReplicationPack:
    validate_pack(db, data)
    if data.get("status") == "REJECTED" and not (data.get("rejection_reason") or "").strip():
        raise ReplicationError("拒绝复制时必须填写拒绝理由")
    if data.get("status") == "PUBLISHED":
        merged_conditions = data.get("conditions", row.conditions)
        merged_evidence = data.get("benefit_evidence", row.benefit_evidence)
        if not (merged_conditions or "").strip() or not (merged_evidence or "").strip():
            raise ReplicationError("发布资产包前必须填写适用条件与收益证据")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def list_packs(
    db: Session,
    source_project_id: Optional[int] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[ReplicationPack]:
    stmt = (
        select(ReplicationPack)
        .options(joinedload(ReplicationPack.source_project))
        .order_by(ReplicationPack.updated_at.desc(), ReplicationPack.id.desc())
    )
    if source_project_id is not None:
        stmt = stmt.where(ReplicationPack.source_project_id == source_project_id)
    if status:
        stmt = stmt.where(ReplicationPack.status == status)
    return list(db.scalars(stmt.limit(limit)).all())
