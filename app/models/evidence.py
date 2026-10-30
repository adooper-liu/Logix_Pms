"""项目判断的主张、反证、证据与裁决记录。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ProjectEvidenceClaim(Base):
    __tablename__ = "project_evidence_claim"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    claim: Mapped[str] = mapped_column(Text)
    counterevidence: Mapped[str] = mapped_column(Text)
    evidence_level: Mapped[str] = mapped_column(String(2), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    gate_condition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "project_gate_condition.id",
            ondelete="SET NULL",
            name="fk_project_evidence_claim_gate_condition",
        ),
        nullable=True,
        index=True,
    )
    source_description: Mapped[str] = mapped_column(Text)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sample_scope: Mapped[str] = mapped_column(Text)
    finding: Mapped[str] = mapped_column(Text)
    verdict: Mapped[str] = mapped_column(
        String(16), default="PENDING", server_default="PENDING", index=True
    )
    decision_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    decided_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="evidence_claims")  # noqa: F821
    created_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[created_by_user_id]
    )
    decided_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[decided_by_user_id]
    )

    __table_args__ = (Index("ix_evidence_claim_project_verdict", "project_id", "verdict"),)
