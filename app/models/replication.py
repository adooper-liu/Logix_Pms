"""复制资产包：把一次改善的适用条件、资产、证据与失败经验打包复用。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ReplicationPack(Base):
    __tablename__ = "replication_pack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200))
    conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    benefit_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    failure_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT", server_default="DRAFT", index=True
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_ids: Mapped[Any] = mapped_column(JSON, default=list)
    document_ids: Mapped[Any] = mapped_column(JSON, default=list)
    template_ids: Mapped[Any] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    source_project: Mapped[Optional["Project"]] = relationship("Project")  # noqa: F821
    owner: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[owner_user_id]
    )

    __table_args__ = (Index("ix_replication_pack_project_status", "source_project_id", "status"),)
