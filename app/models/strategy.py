"""战略域模型：年度目标与「目标 → 流程 → KPI」的承接关系。

设计要点：
- 目标本身只记录「赢什么、目标值、责任人、来源」；
- 承接关系放在独立的链接表里，一条目标可以承接多个 L1/L2/L3 流程与 KPI；
- 流程卡反查时按祖先继承：目标挂在 L1/L2，L3/L4 也能看到。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class StrategyObjective(Base):
    __tablename__ = "strategy_objective"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    year: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(
        String(16), default="ANNUAL", server_default="ANNUAL", index=True
    )
    baseline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    source_document: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_objective_owner_user"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", server_default="ACTIVE", index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    links: Mapped[List["ObjectiveProcessLink"]] = relationship(
        "ObjectiveProcessLink",
        back_populates="objective",
        cascade="all, delete-orphan",
        order_by="ObjectiveProcessLink.id",
    )

    __table_args__ = (Index("ix_objective_year_status", "year", "status"),)


class ObjectiveProcessLink(Base):
    """目标承接：目标 → 流程（任意层级）→ 可选 KPI。"""

    __tablename__ = "objective_process_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    objective_id: Mapped[int] = mapped_column(
        ForeignKey("strategy_objective.id", ondelete="CASCADE", name="fk_link_objective"),
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_link_process"),
        index=True,
    )
    kpi_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kpi_definition.id", ondelete="SET NULL", name="fk_link_kpi"),
        nullable=True,
        index=True,
    )
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    objective: Mapped["StrategyObjective"] = relationship(
        "StrategyObjective", back_populates="links"
    )
    process: Mapped["ProcessArch"] = relationship("ProcessArch")  # noqa: F821
    kpi: Mapped[Optional["KpiDefinition"]] = relationship("KpiDefinition")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("objective_id", "process_id", "kpi_id", name="uq_objective_process_kpi"),
        Index("ix_objective_link_process", "process_id", "kpi_id"),
    )
