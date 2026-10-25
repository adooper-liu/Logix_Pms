"""成熟度评估与阶段门禁证据。

成熟度回答「这条流程在治理/资产/数据/执行/度量上到几级」；
门禁回答「这次项目能不能进入下一阶段、依据是什么、谁签收」。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class MaturityAssessment(Base):
    __tablename__ = "maturity_assessment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL"), nullable=True, index=True
    )
    dimension: Mapped[str] = mapped_column(String(32), index=True)
    level: Mapped[int] = mapped_column(Integer)  # 0–5
    evidence_url: Mapped[str] = mapped_column(String(500))
    assessed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assessed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    valid_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    process: Mapped["ProcessArch"] = relationship("ProcessArch")  # noqa: F821
    assessed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[assessed_by_user_id]
    )

    __table_args__ = (Index("ix_maturity_process_dimension", "process_id", "dimension"),)


class GateAttestation(Base):
    __tablename__ = "gate_attestation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    stage_no: Mapped[int] = mapped_column(Integer, index=True)  # 1–5
    gate_code: Mapped[str] = mapped_column(
        String(32), default="STAGE_GATE", server_default="STAGE_GATE"
    )
    exit_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[str] = mapped_column(String(500))
    conclusion: Mapped[str] = mapped_column(String(16), index=True)  # GateConclusion
    signed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    signed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    signed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[signed_by_user_id]
    )

    __table_args__ = (Index("ix_gate_project_stage", "project_id", "stage_no"),)
