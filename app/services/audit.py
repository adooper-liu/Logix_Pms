"""审计留痕。"""

from __future__ import annotations

import hashlib
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.user import AuditLog, User


def _digest(prev_hash: Optional[str], entry: AuditLog) -> str:
    payload = "|".join(
        [
            prev_hash or "",
            str(entry.user_id or ""),
            entry.username or "",
            entry.action or "",
            entry.entity_type or "",
            str(entry.entity_id if entry.entity_id is not None else ""),
            entry.summary or "",
            entry.created_at.isoformat() if entry.created_at else "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record(
    db: Session,
    user: Optional[User],
    action: str,
    entity_type: str,
    entity_id: Optional[int] = None,
    summary: Optional[str] = None,
) -> AuditLog:
    """登记一条写操作，并接上哈希链。调用方负责 commit。"""
    db.flush()
    previous = db.scalar(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    prev_hash = previous.hash if previous else None
    entry = AuditLog(
        user_id=user.id if user else None,
        username=user.username if user else "system",
        display_name=user.display_name if user else "系统",
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        created_at=utcnow(),
        prev_hash=prev_hash,
    )
    entry.hash = _digest(prev_hash, entry)
    db.add(entry)
    db.flush()
    return entry


def verify_chain(db: Session, limit: int = 10000) -> dict:
    rows = list(db.scalars(select(AuditLog).order_by(AuditLog.id).limit(limit)).all())
    prev: Optional[str] = None
    for index, row in enumerate(rows):
        if row.prev_hash != prev:
            return {"ok": False, "checked": index, "broken_at": row.id}
        expected = _digest(prev, row)
        if row.hash != expected:
            return {"ok": False, "checked": index, "broken_at": row.id}
        prev = row.hash
    return {"ok": True, "checked": len(rows), "broken_at": None}
