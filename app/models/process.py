"""流程域模型：流程架构（L1–L4）、流程节点、流程连线。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


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

    # owner 是展示用的姓名/岗位标签；owner_user_id 才是权限判断的唯一依据
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_arch_owner_user_id_app_user",
        ),
        nullable=True,
        index=True,
    )
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_process_arch_org_unit"),
        nullable=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 价值-痛点矩阵三个维度，1–5 分
    strategic_importance: Mapped[float] = mapped_column(Float, default=3.0)
    pain_score: Mapped[float] = mapped_column(Float, default=3.0)
    improvement_space: Mapped[float] = mapped_column(Float, default=3.0)

    health_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0–100
    is_improvement_target: Mapped[bool] = mapped_column(Boolean, default=False)

    # 由标准分类树（APQC PCF）生成的架构草稿：确认后清除 is_draft，
    # source_* 保留来源，保证重复生成时能识别并跳过已有节点。
    is_draft: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    source_framework_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source_external_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    # 流程模型的并发控制：每次整份保存 +1，客户端提交时带上自己看到的版本
    model_version: Mapped[int] = mapped_column(Integer, default=0)
    # 最近一次发布到运行时的版本；新实例按这个版本快照
    published_model_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
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
    nodes: Mapped[List["ProcessNode"]] = relationship(
        "ProcessNode",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="ProcessNode.sequence_order",
        foreign_keys="ProcessNode.process_id",
    )
    edges: Mapped[List["ProcessEdge"]] = relationship(
        "ProcessEdge",
        back_populates="process",
        cascade="all, delete-orphan",
    )
    model_versions: Mapped[List["ProcessModelVersion"]] = relationship(
        "ProcessModelVersion",
        back_populates="process",
        cascade="all, delete-orphan",
        order_by="ProcessModelVersion.version",
    )
    node_assignments: Mapped[List["NodeAssignment"]] = relationship(  # noqa: F821
        "NodeAssignment",
        back_populates="process",
        cascade="all, delete-orphan",
    )
    org_unit: Mapped[Optional["OrgUnit"]] = relationship("OrgUnit")  # noqa: F821

    __table_args__ = (
        Index("ix_process_arch_level_parent", "level", "parent_id"),
        Index("ix_process_arch_source", "source_framework_code", "source_external_id"),
    )

    @property
    def priority_score(self) -> float:
        """价值-痛点综合得分，用于优先级排序。"""
        return round(self.strategic_importance * self.pain_score * self.improvement_space, 3)

    @property
    def org_unit_name(self) -> Optional[str]:
        return self.org_unit.name if self.org_unit else None


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
    # 统一活动 ID：指向 L3 流程下面的 L4 活动；NULL = 尚未关联
    process_arch_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_process_node_activity"),
        nullable=True,
        index=True,
    )
    owner_position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL", name="fk_process_node_position"),
        nullable=True,
        index=True,
    )

    duration_minutes: Mapped[float] = mapped_column(Float, default=0.0)  # 作业时间
    wait_minutes: Mapped[float] = mapped_column(Float, default=0.0)  # 等待/排队时间
    cost: Mapped[float] = mapped_column(Float, default=0.0)  # 单次执行成本
    rework_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 0–1 返工率
    approval_levels: Mapped[int] = mapped_column(Integer, default=0)  # 审批层级数
    is_value_added: Mapped[bool] = mapped_column(Boolean, default=True)

    sequence_order: Mapped[int] = mapped_column(Integer, default=0)
    position_x: Mapped[float] = mapped_column(Float, default=0.0)
    position_y: Mapped[float] = mapped_column(Float, default=0.0)

    process: Mapped["ProcessArch"] = relationship(
        "ProcessArch",
        back_populates="nodes",
        foreign_keys=[process_id],
    )
    activity: Mapped[Optional["ProcessArch"]] = relationship(
        "ProcessArch",
        foreign_keys=[process_arch_id],
    )
    owner_position: Mapped[Optional["Position"]] = relationship("Position")  # noqa: F821

    __table_args__ = (Index("ix_process_node_process_key", "process_id", "node_key", unique=True),)


class NodeTool(Base):
    """活动级工具绑定：某个流程节点推荐/要求使用哪个方法论工具。"""

    __tablename__ = "node_tool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    tool_code: Mapped[str] = mapped_column(ForeignKey("tool.code", ondelete="CASCADE"), index=True)
    level: Mapped[str] = mapped_column(String(16), default="RECOMMENDED")
    note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    tool: Mapped["Tool"] = relationship("Tool")  # noqa: F821

    @property
    def tool_name(self) -> Optional[str]:
        return self.tool.name if self.tool else None

    __table_args__ = (
        Index("ix_node_tool_process_node", "process_id", "node_key"),
        Index("uq_node_tool_binding", "process_id", "node_key", "tool_code", unique=True),
    )


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

    process: Mapped["ProcessArch"] = relationship("ProcessArch", back_populates="edges")

    __table_args__ = (Index("ix_process_edge_process", "process_id"),)


class ProcessModelVersion(Base):
    """流程模型版本：草稿、评审、发布与回滚。

    `snapshot` 是整张图（节点 + 连线）的不可变副本；`process_node/process_edge`
    只保存**已发布**模型，执行引擎只读它们。这样草稿编辑不会影响运行中的实例。
    """

    __tablename__ = "process_model_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_arch.id",
            ondelete="CASCADE",
            name="fk_process_model_version_process",
        ),
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    # bpmn-js 的完整 XML（含 DI 坐标/连线折点/泳道）；用于还原用户的版面调整
    bpmn_xml: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_model_version_created_by",
        ),
        nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    reviewed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_model_version_reviewed_by",
        ),
        nullable=True,
    )
    reviewed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    published_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_model_version_published_by",
        ),
        nullable=True,
    )
    published_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    process: Mapped["ProcessArch"] = relationship("ProcessArch", back_populates="model_versions")

    __table_args__ = (
        Index(
            "uq_process_model_version_process_version",
            "process_id",
            "version",
            unique=True,
        ),
    )
