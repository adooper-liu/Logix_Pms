"""BPMN 元素评论：节点/连线的评审讨论与解决状态。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessComment(Base):
    __tablename__ = "process_comment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    element_id: Mapped[str] = mapped_column(String(64), index=True)
    element_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    element_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="OPEN", server_default="OPEN", index=True
    )
    author_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    author: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[author_user_id]
    )
    resolved_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[resolved_by_user_id]
    )

    __table_args__ = (
        Index("ix_process_comment_process_element", "process_id", "element_id"),
        Index("ix_process_comment_process_status", "process_id", "status"),
    )
