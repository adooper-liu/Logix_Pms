"""流程域模型：流程架构（L1–L4）、流程节点、流程连线。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProcessArch(Base):
    """企业流程地图的节点，按 L1 价值链 → L4 活动分层。"""

    __tablename__ = "process_arch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    level: Mapped[int] = mapped_column(Integer, index=True)  # 1..4
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), nullable=True, index=True
    )

    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 价值-痛点矩阵三个维度，1–5 分
    strategic_importance: Mapped[float] = mapped_column(Float, default=3.0)
    pain_score: Mapped[float] = mapped_column(Float, default=3.0)
    improvement_space: Mapped[float] = mapped_column(Float, default=3.0)

    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0–100
    is_improvement_target: Mapped[bool] = mapped_column(Boolean, default=False)

    # 流程模型的并发控制：每次整份保存 +1，客户端提交时带上自己看到的版本
    model_version: Mapped[int] = mapped_column(Integer, default=0)
    model_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    children: Mapped[List["ProcessArch"]] = relationship(
        "ProcessArch",
        back_populates="parent",
        cascade="all, delete-orphan",
        order_by="ProcessArch.code",
    )
    parent: Mapped[Optional["ProcessArch"]] = relationship(
        "ProcessArch", back_populates="children", remote_side="ProcessArch.id"
    )

    __table_args__ = (Index("ix_process_arch_level_parent", "level", "parent_id"),)

    @property
    def priority_score(self) -> float:
        """价值-痛点综合得分，用于优先级排序。"""
        return round(self.strategic_importance * self.pain_score * self.improvement_space, 3)


class ProcessNode(Base):
    """流程设计器中的节点（含泳道归属），可直接用于周期效率测算。"""

    __tablename__ = "process_node"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )

    node_key: Mapped[str] = mapped_column(String(64))  # 流程内唯一键，连线用它引用
    name: Mapped[str] = mapped_column(String(128))
    node_type: Mapped[str] = mapped_column(String(16))
    lane: Mapped[str] = mapped_column(String(64), default="主流程")  # 泳道 = 部门/角色

    owner_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)  # 作业时间
    wait_minutes: Mapped[float] = mapped_column(Float, default=0.0)  # 等待/排队时间
    cost: Mapped[float] = mapped_column(Float, default=0.0)  # 单次执行成本
    rework_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 0–1 返工率
    approval_levels: Mapped[int] = mapped_column(Integer, default=0)  # 审批层级数
    is_value_added: Mapped[bool] = mapped_column(Boolean, default=True)

    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)

    __table_args__ = (Index("ix_process_node_process_key", "process_id", "node_key", unique=True),)


class ProcessEdge(Base):
    """流程连线。source/target 用 node_key 引用，便于整体覆盖式保存模型。"""

    __tablename__ = "process_edge"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )

    source_key: Mapped[str] = mapped_column(String(64))
    target_key: Mapped[str] = mapped_column(String(64))
    label: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    condition: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    probability: Mapped[float] = mapped_column(Float, default=1.0)  # 分支发生概率 0–1

    __table_args__ = (Index("ix_process_edge_process", "process_id"),)
