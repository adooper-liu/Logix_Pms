"""运营监控域模型：KPI 定义、KPI 时序数据、异常事件。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class KpiDefinition(Base):
    """KPI 定义卡：四维度（效率/质量/成本/灵活性）× 三类（结果/过程/健康度）。

    `dimension` 用于雷达图的四维汇总；`kind` 用于区分结果、过程与健康度，
    两者正交。定义卡要求写清公式、分子分母、粒度、频率、数据来源与阈值，
    避免不同部门用同一个指标名却算出不同口径。
    """

    __tablename__ = "kpi_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    dimension: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(
        String(16), default="PROCESS", server_default="PROCESS", index=True
    )
    direction: Mapped[str] = mapped_column(String(16), default="LOWER_BETTER")

    unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 定义卡字段：口径必须可复核，不能只靠指标名
    formula: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    numerator: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    denominator: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    granularity: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    frequency: Mapped[str] = mapped_column(
        String(16), default="MONTHLY", server_default="MONTHLY", index=True
    )
    source_system: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 数据流台账上的来源。选定后，source_system 跟这条流的来源系统走。
    data_flow_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "data_flow.id",
            ondelete="SET NULL",
            name="fk_kpi_definition_data_flow",
        ),
        nullable=True,
        index=True,
    )
    # 非时长指标的正式写入口。未启用、或不允许回传指标时，这条 KPI 不进红黄。
    inbound_webhook_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "inbound_webhook.id",
            ondelete="SET NULL",
            name="fk_kpi_definition_inbound_webhook",
        ),
        nullable=True,
        index=True,
    )
    quality_rule: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    measurement: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # 红/黄/绿三条线：红=最差边界，绿=达标边界，黄为两者之间
    red_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    yellow_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    green_threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 可进一步绑到 L4 活动；与 process_id 同时存在时必须属于该流程
    activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_kpi_activity"),
        nullable=True,
        index=True,
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_kpi_owner_user"),
        nullable=True,
        index=True,
    )

    # 定义版本：只在口径字段变更时 +1；数据点追加不影响
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
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
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    # 从红黄指标或超时任务带出、经人确认后写入。空着表示人手登记。
    source_kpi_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "kpi_definition.id",
            ondelete="SET NULL",
            name="fk_exception_event_source_kpi",
        ),
        nullable=True,
        index=True,
    )
    source_instance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_instance.id",
            ondelete="SET NULL",
            name="fk_exception_event_source_instance",
        ),
        nullable=True,
        index=True,
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
    resolution: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    __table_args__ = (Index("ix_exception_status_severity", "status", "severity"),)
