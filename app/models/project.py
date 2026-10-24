"""项目域模型：流程项目、项目五阶段步骤实例、标准工作流模板。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class Project(Base):
    """流程项目（BPR / BPI / 精益 / 混合）。"""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    methodology: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="PLANNING")
    current_stage: Mapped[int] = mapped_column(Integer, default=1)  # 1..5
    priority: Mapped[int] = mapped_column(Integer, default=3)  # 1 最高，5 最低

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # owner 是展示用的姓名/岗位标签；owner_user_id 才是权限判断的唯一依据。
    # 两者在写入时一起维护（绑定账号就把标签同步成该用户的 display_name）。
    owner: Mapped[str] = mapped_column(String(64))
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_project_owner_user_id_app_user",
        ),
        nullable=True,
        index=True,
    )
    sponsor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    objective: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    metric_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    baseline_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    improvement_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 目标改善幅度 %

    # 改善项目卡：来源、问题、根因、对策、验证、收益与复制
    source: Mapped[str] = mapped_column(
        String(24), default="MANUAL", server_default="MANUAL", index=True
    )
    source_kpi_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kpi_definition.id", ondelete="SET NULL", name="fk_project_source_kpi"),
        nullable=True,
        index=True,
    )
    problem_statement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    countermeasure: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    benefit: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    observation_until: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    one_time_cost: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    transfer_cost: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    replication_status: Mapped[str] = mapped_column(
        String(20), default="NOT_EVALUATED", server_default="NOT_EVALUATED", index=True
    )
    replication_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    budget: Mapped[float] = mapped_column(Float, default=0.0)
    actual_cost: Mapped[float] = mapped_column(Float, default=0.0)
    roi_estimate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0–100

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    steps: Mapped[List["ProjectStep"]] = relationship(
        "ProjectStep",
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="ProjectStep.stage_no, ProjectStep.step_no",
    )
    source_kpi: Mapped[Optional["KpiDefinition"]] = relationship("KpiDefinition")  # noqa: F821

    __table_args__ = (Index("ix_project_status_stage", "status", "current_stage"),)


class ProjectStep(Base):
    """项目在某一步骤上的执行实例，源自标准工作流模板。"""

    __tablename__ = "project_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )

    stage_no: Mapped[int] = mapped_column(Integer)
    step_no: Mapped[str] = mapped_column(String(8))  # "1.1"、"3.4"
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")

    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    deliverable: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    # 每个阶段的最后一步作为里程碑（决策门），在甘特图上以菱形标记
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped["Project"] = relationship("Project", back_populates="steps")
    deliverables: Mapped[List["DeliverableInstance"]] = relationship(  # noqa: F821
        "DeliverableInstance",
        back_populates="step",
        cascade="all, delete-orphan",
    )

    __table_args__ = (Index("ix_project_step_project", "project_id", "stage_no", "step_no"),)


class WorkflowTemplate(Base):
    """五阶段标准工作流模板（全公司共用的一套操作手册）。"""

    __tablename__ = "workflow_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage_no: Mapped[int] = mapped_column(Integer, index=True)
    stage_name: Mapped[str] = mapped_column(String(64))
    stage_goal: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    step_no: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(Text)
    tools: Mapped[str] = mapped_column(String(200))  # 逗号分隔的工具名
    deliverables: Mapped[str] = mapped_column(String(200))  # 交付物
    key_points: Mapped[str] = mapped_column(Text)  # 关键要点 / 踩坑提示

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_mandatory: Mapped[bool] = mapped_column(Boolean, default=True)
