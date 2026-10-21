"""运营监控域模型：KPI 定义、KPI 时序数据、异常事件。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class KpiDefinition(Base):
    """KPI 定义。四维度：效率 / 质量 / 成本 / 灵活性。"""

    __tablename__ = "kpi_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[str] = mapped_column(String(16), index=True)
    direction: Mapped[str] = mapped_column(String(16), default="LOWER_BETTER")

    unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    records: Mapped[List["KpiRecord"]] = relationship(
        "KpiRecord",
        back_populates="kpi",
        cascade="all, delete-orphan",
        order_by="KpiRecord.period",
    )


class KpiRecord(Base):
    """KPI 时序数据（按月/按周记录）。"""

    __tablename__ = "kpi_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kpi_id: Mapped[int] = mapped_column(
        ForeignKey("kpi_definition.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )

    period: Mapped[date] = mapped_column(Date, index=True)
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    kpi: Mapped["KpiDefinition"] = relationship("KpiDefinition", back_populates="records")

    __table_args__ = (Index("ix_kpi_record_kpi_period", "kpi_id", "period"),)


class ExceptionEvent(Base):
    """流程异常事件，闭环管理：发现 → 处理 → 解决 → 关闭。"""

    __tablename__ = "exception_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )

    title: Mapped[str] = mapped_column(String(160))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), index=True, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(16), index=True, default="OPEN")

    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_exception_event_owner_user_id_app_user",
        ),
        nullable=True,
        index=True,
    )
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_taken: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (Index("ix_exception_status_severity", "status", "severity"),)
