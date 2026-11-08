"""客户 / 市场 / 合规要求：目标的上游输入，可挂多个战略目标。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class MarketRequirement(Base):
    __tablename__ = "market_requirement"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(16), index=True)
    title: Mapped[str] = mapped_column(String(160))
    requirement: Mapped[str] = mapped_column(Text)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", server_default="ACTIVE", index=True
    )
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_requirement_creator"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_requirement_status_type", "status", "source_type"),)


class RequirementObjectiveLink(Base):
    __tablename__ = "requirement_objective_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    requirement_id: Mapped[int] = mapped_column(
        ForeignKey(
            "market_requirement.id",
            ondelete="CASCADE",
            name="fk_requirement_link_requirement",
        ),
        index=True,
    )
    objective_id: Mapped[int] = mapped_column(
        ForeignKey(
            "strategy_objective.id", ondelete="CASCADE", name="fk_requirement_link_objective"
        ),
        index=True,
    )
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("requirement_id", "objective_id", name="uq_requirement_objective"),
        Index("ix_requirement_link_objective", "objective_id", "requirement_id"),
    )
