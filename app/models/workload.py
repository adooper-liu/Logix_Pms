"""工作量域模型：标准工时研究与产能日历。

设计约束：
- 标准工时绑定「L4 活动 × 岗位」，并记录方法、条件、样本、评定与宽放；
- 只有 `VERIFIED` 的标准进入产能/成本口径，草稿与估算明确标注；
- 实际工时继续复用 `TaskWorklog`，这里只补「标准」和「可用产能」两端。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
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


class WorkMeasurementStandard(Base):
    """标准工时卡：活动 × 岗位 × 适用条件下的标准作业时间。"""

    __tablename__ = "work_measurement_standard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))

    # 活动必须是 L4；岗位是产能与绩效归集的稳定口径
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_wms_activity"),
        index=True,
    )
    # 可选绑定到 L5 任务；绑定后 L4 标准工时可由任务汇总
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_task_definition.id", ondelete="SET NULL", name="fk_wms_task"),
        nullable=True,
        index=True,
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("position.id", ondelete="RESTRICT", name="fk_wms_position"),
        index=True,
    )
    # 标准适用组织；NULL = 集团通用
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_wms_org_unit"),
        nullable=True,
        index=True,
    )

    method_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), default="TIME_STUDY", server_default="TIME_STUDY", index=True
    )

    # 观测时间 × 评定系数 × (1 + 宽放率) = 标准工时
    observed_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    rating_factor: Mapped[float] = mapped_column(Float, default=1.0)
    allowance_rate: Mapped[float] = mapped_column(Float, default=0.0)
    standard_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    # 计划频次（次/月），用于把单次标准工时换算成月度需求
    monthly_frequency: Mapped[float] = mapped_column(Float, default=0.0)

    status: Mapped[str] = mapped_column(
        String(16), default="DRAFT", server_default="DRAFT", index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verified_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_wms_verified_by"),
        nullable=True,
    )
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_wms_created_by"),
        nullable=True,
    )
    # 评审人：与“验证人”分开，保留“谁观测、谁审核”的责任链
    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_wms_reviewed_by"),
        nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    activity: Mapped["ProcessArch"] = relationship(  # noqa: F821
        "ProcessArch", foreign_keys=[activity_id]
    )
    task: Mapped[Optional["ProcessTaskDefinition"]] = relationship(  # noqa: F821
        "ProcessTaskDefinition", foreign_keys=[task_id]
    )
    position: Mapped["Position"] = relationship("Position")  # noqa: F821
    org_unit: Mapped[Optional["OrgUnit"]] = relationship("OrgUnit")  # noqa: F821
    verified_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[verified_by_id]
    )
    reviewed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[reviewed_by_id]
    )
    observations: Mapped[list["WorkMeasurementObservation"]] = relationship(
        "WorkMeasurementObservation",
        back_populates="standard",
        cascade="all, delete-orphan",
        order_by="WorkMeasurementObservation.sequence",
    )

    __table_args__ = (
        Index("ix_wms_activity_position", "activity_id", "position_id"),
        Index("ix_wms_position_status", "position_id", "status"),
    )


class WorkMeasurementObservation(Base):
    """一次现场观测记录：均值、样本量由这些记录自动回算。"""

    __tablename__ = "work_measurement_observation"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    standard_id: Mapped[int] = mapped_column(
        ForeignKey(
            "work_measurement_standard.id",
            ondelete="CASCADE",
            name="fk_wms_observation_standard",
        ),
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    observed_minutes: Mapped[float] = mapped_column(Float)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    observer_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_wms_observation_observer"),
        nullable=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    standard: Mapped["WorkMeasurementStandard"] = relationship(
        "WorkMeasurementStandard", back_populates="observations"
    )
    observer: Mapped[Optional["User"]] = relationship("User")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("standard_id", "sequence", name="uq_wms_observation_sequence"),
    )


class CapacityCalendar(Base):
    """产能日历：某组织某岗位在某期间的人力与可用工时。"""

    __tablename__ = "capacity_calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    org_unit_id: Mapped[int] = mapped_column(
        ForeignKey("org_unit.id", ondelete="CASCADE", name="fk_capacity_org_unit"),
        index=True,
    )
    position_id: Mapped[int] = mapped_column(
        ForeignKey("position.id", ondelete="RESTRICT", name="fk_capacity_position"),
        index=True,
    )
    period: Mapped[date] = mapped_column(Date, index=True)

    headcount: Mapped[float] = mapped_column(Float, default=0.0)
    available_hours_per_person: Mapped[float] = mapped_column(Float, default=0.0)
    attendance_rate: Mapped[float] = mapped_column(Float, default=1.0)
    equipment_availability: Mapped[float] = mapped_column(Float, default=1.0)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    org_unit: Mapped["OrgUnit"] = relationship("OrgUnit")  # noqa: F821
    position: Mapped["Position"] = relationship("Position")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "org_unit_id", "position_id", "period", name="uq_capacity_org_position_period"
        ),
    )
