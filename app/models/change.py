"""变更治理：流程变更申请与影响分析。

变更单是发布门禁的证据载体：
- 重大变更（MAJOR）必须写全影响分析、测试证据与回退方案；
- 已批准的变更单才能用于门禁流程的发布；
- 发布成功后变更单进入 APPLIED，并记录到模型版本上。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessChangeRequest(Base):
    __tablename__ = "process_change_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_change_process"),
        index=True,
    )

    title: Mapped[str] = mapped_column(String(160))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_type: Mapped[str] = mapped_column(
        String(16), default="STRUCTURE", server_default="STRUCTURE", index=True
    )
    impact_level: Mapped[str] = mapped_column(
        String(16), default="MINOR", server_default="MINOR", index=True
    )
    version_label: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)

    # {people, systems, data, permissions, controls, training, kpis}
    impact: Mapped[dict] = mapped_column(JSON, default=dict)
    test_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rollback_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    emergency: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())

    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT", server_default="DRAFT", index=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    requested_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_change_requested_by"),
        nullable=True,
    )
    requested_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_change_approved_by"),
        nullable=True,
    )
    approved_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    process: Mapped["ProcessArch"] = relationship("ProcessArch")  # noqa: F821

    __table_args__ = (Index("ix_change_process_status", "process_id", "status"),)
