"""Generic process operating lifecycle and gate records."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessOperatingCycle(Base):
    __tablename__ = "process_operating_cycle"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supersedes_cycle_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_operating_cycle.id", ondelete="SET NULL"), nullable=True, index=True
    )
    launch_authorizer_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    launch_authorizer_scope: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    cycle_type: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index(
        "uq_operating_cycle_active",
        "process_id",
        unique=True,
        postgresql_where=text("status = 'ACTIVE'"),
        sqlite_where=text("status = 'ACTIVE'"),
    ),)


class ProcessGateAssessment(Base):
    __tablename__ = "process_gate_assessment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("process_operating_cycle.id", ondelete="CASCADE"), index=True
    )
    gate_key: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(20), default="NOT_STARTED")
    applicability: Mapped[str] = mapped_column(String(20), default="APPLICABLE")
    rigor: Mapped[str] = mapped_column(String(16), default="STANDARD")
    applicability_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verifier_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    risk_level: Mapped[str] = mapped_column(String(16), default="NORMAL")
    conclusion: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_action_ref: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_current: Mapped[bool] = mapped_column(default=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("cycle_id", "gate_key", "revision", name="uq_gate_revision"),)

    @property
    def does_not_block_launch(self) -> bool:
        return self.applicability == "NOT_APPLICABLE"


class ProcessGateEvidence(Base):
    __tablename__ = "process_gate_evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gate_assessment_id: Mapped[int] = mapped_column(
        ForeignKey("process_gate_assessment.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(String(48), index=True)
    source_id: Mapped[str] = mapped_column(String(128))
    source_version_or_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    evidence_grade: Mapped[str] = mapped_column(String(4), default="E0")
    verification_status: Mapped[str] = mapped_column(String(20), default="UNVERIFIED")
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    verification_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ProcessOperatingDecision(Base):
    __tablename__ = "process_operating_decision"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("process_operating_cycle.id", ondelete="CASCADE"), index=True
    )
    decision_type: Mapped[str] = mapped_column(String(32), index=True)
    decision: Mapped[str] = mapped_column(String(20))
    decision_by_user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id"), index=True)
    authority_basis: Mapped[str] = mapped_column(String(64))
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_snapshot: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    valid_scope: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    follow_up_due: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
