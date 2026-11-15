"""Version-bound responsibility acceptance evidence for generic Gate 5."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessResponsibilityAcceptance(Base):
    __tablename__ = "process_responsibility_acceptance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(24), index=True)
    subject_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    accepted_by_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    accepted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    evidence_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="ACCEPTED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        Index(
            "uq_responsibility_acceptance_current",
            "process_id",
            "model_version_id",
            "node_key",
            "scope",
            "subject_user_id",
            unique=True,
            postgresql_where=text("status = 'ACCEPTED'"),
            sqlite_where=text("status = 'ACCEPTED'"),
        ),
    )
