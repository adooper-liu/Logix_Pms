"""CSV 事件日志导入：原始事件、活动映射与实测指标。

日志是观测来源，不是模型；提交时只生成 LOGGED 证据主张，不改 BPMN。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessLogImport(Base):
    __tablename__ = "process_log_import"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_log_import_process"),
        index=True,
    )
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_model_version.id",
            ondelete="SET NULL",
            name="fk_log_import_model_version",
        ),
        nullable=True,
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(255))
    checksum: Mapped[str] = mapped_column(String(64))
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    case_count: Mapped[int] = mapped_column(Integer, default=0)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # DRAFT / MAPPED / COMMITTED
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    mapping: Mapped[Any] = mapped_column(JSON, default=dict)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    claim_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("evidence_claim.id", ondelete="SET NULL", name="fk_log_import_claim"),
        nullable=True,
        index=True,
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_log_import_creator"),
        nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    events: Mapped[List["ProcessLogEvent"]] = relationship(
        "ProcessLogEvent",
        back_populates="import_row",
        cascade="all, delete-orphan",
        order_by="ProcessLogEvent.id",
    )


class ProcessLogEvent(Base):
    __tablename__ = "process_log_event"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    import_id: Mapped[int] = mapped_column(
        ForeignKey("process_log_import.id", ondelete="CASCADE", name="fk_log_event_import"),
        index=True,
    )
    case_id: Mapped[str] = mapped_column(String(64), index=True)
    activity_label: Mapped[str] = mapped_column(String(200), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    resource: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    mapped_activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_log_event_activity"),
        nullable=True,
        index=True,
    )

    import_row: Mapped["ProcessLogImport"] = relationship(
        "ProcessLogImport", back_populates="events"
    )

    __table_args__ = (
        Index("ix_log_event_import_case_time", "import_id", "case_id", "occurred_at"),
    )


class LogComparisonReceipt(Base):
    """前后对照的接收记录：结论是否被人工接收，以及能否据此宣称改善。"""

    __tablename__ = "log_comparison_receipt"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_log_receipt_process"),
        index=True,
    )
    before_import_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_log_import.id",
            ondelete="CASCADE",
            name="fk_log_receipt_before",
        ),
        index=True,
    )
    after_import_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_log_import.id",
            ondelete="CASCADE",
            name="fk_log_receipt_after",
        ),
        index=True,
    )
    # ACCEPT / RETURN / OBSERVE
    decision: Mapped[str] = mapped_column(String(16), index=True)
    rationale: Mapped[str] = mapped_column(Text)
    comparable: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    sample_ok: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    claim_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", index=True
    )
    metrics: Mapped[Any] = mapped_column(JSON, default=dict)
    conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    accepted_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_log_receipt_user"),
        nullable=True,
    )
    accepted_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index(
            "ix_log_receipt_pair",
            "process_id",
            "before_import_id",
            "after_import_id",
            "id",
        ),
    )
