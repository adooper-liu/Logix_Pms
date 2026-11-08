"""文档候选活动：从制度/操作文档抽出的候选步骤，人工确认后才进入流程架构。

刻意只写 `process_arch` 的 L4 活动，不自动改 BPMN 模型；候选不是 As-Is 实测。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class DocumentCandidateActivity(Base):
    __tablename__ = "document_candidate_activity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_version_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_document_version.id",
            ondelete="CASCADE",
            name="fk_document_candidate_version",
        ),
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_document_candidate_process"),
        index=True,
    )
    line_no: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[str] = mapped_column(String(16), default="NUMBERED")
    # PROPOSED / CONFIRMED / REJECTED
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)
    activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_document_candidate_activity"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_document_candidate_creator"),
        nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_document_candidate_confirmer"),
        nullable=True,
    )
    confirmed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("document_version_id", "line_no", name="uq_document_candidate_line"),
        Index("ix_document_candidate_process_status", "process_id", "status"),
    )
