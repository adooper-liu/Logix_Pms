"""BPMN 元素评论服务。"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.collaboration import ProcessComment
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.collaboration import CommentOut

STATUS_LABELS = {"OPEN": "待处理", "RESOLVED": "已解决"}


def comment_out(row: ProcessComment) -> CommentOut:
    return CommentOut(
        id=row.id,
        process_id=row.process_id,
        element_id=row.element_id,
        element_name=row.element_name,
        element_type=row.element_type,
        body=row.body,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        author_user_id=row.author_user_id,
        author_name=row.author_name,
        resolved_by_user_id=row.resolved_by_user_id,
        resolved_by_name=row.resolved_by.display_name if row.resolved_by else None,
        resolved_at=row.resolved_at,
        created_at=row.created_at,
    )


def require_process(db: Session, process_id: int) -> ProcessArch:
    process = db.get(ProcessArch, process_id)
    if process is None:
        raise ValueError("流程不存在")
    return process


def list_comments(
    db: Session,
    process_id: int,
    element_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 200,
) -> List[ProcessComment]:
    require_process(db, process_id)
    stmt = (
        select(ProcessComment)
        .options(selectinload(ProcessComment.resolved_by))
        .where(ProcessComment.process_id == process_id)
        .order_by(ProcessComment.created_at.desc(), ProcessComment.id.desc())
    )
    if element_id:
        stmt = stmt.where(ProcessComment.element_id == element_id)
    if status:
        stmt = stmt.where(ProcessComment.status == status)
    return list(db.scalars(stmt.limit(limit)).all())


def create_comment(db: Session, process_id: int, data: dict, user: User) -> ProcessComment:
    require_process(db, process_id)
    row = ProcessComment(
        process_id=process_id,
        element_id=data["element_id"],
        element_name=data.get("element_name"),
        element_type=data.get("element_type"),
        body=data["body"],
        status="OPEN",
        author_user_id=user.id,
        author_name=user.display_name,
    )
    db.add(row)
    db.flush()
    return row


def resolve_comment(db: Session, row: ProcessComment, user: User) -> ProcessComment:
    from app.core.timeutil import utcnow

    if row.status == "RESOLVED":
        return row
    row.status = "RESOLVED"
    row.resolved_by_user_id = user.id
    row.resolved_at = utcnow()
    db.flush()
    return row
