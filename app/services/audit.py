"""审计留痕。"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.user import AuditLog, User


def record(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    summary: Optional[str] = None,
) -> AuditLog:
    """登记一条写操作。调用方负责 commit。"""
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        display_name=user.display_name if user else "系统",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
    )
    db.add(entry)
    return entry
