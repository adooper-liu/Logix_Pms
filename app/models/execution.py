"""流程执行域模型：运行时实例与任务队列。

设计边界：
- 当前是**单令牌顺序执行**：一个实例同一时刻只有一个待办任务；遇到分支由处理人选择下一步。
- 并行网关、子流程、定时器留到后续版本；先把「实例 → 任务 → 完成 → 下一任务」跑通。
- 实例启动时对流程模型做快照，之后设计器改动不会影响运行中的实例。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessInstance(Base):
    """一次流程运行。snapshot 保存启动时的节点/连线，保证运行语义稳定。"""

    __tablename__ = "process_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True, index=True
    )
    process_name: Mapped[str] = mapped_column(String(128))
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )

    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)
    current_node_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    current_node_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    definition_version: Mapped[int] = mapped_column(Integer, default=0)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    suspend_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    variables: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    started_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    tasks: Mapped[List["ProcessTask"]] = relationship(
        "ProcessTask",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="ProcessTask.id",
    )

    __table_args__ = (Index("ix_process_instance_status_started", "status", "started_at"),)


class ProcessTask(Base):
    """运行时任务。同一实例同一时刻最多一个 OPEN（PENDING/CLAIMED）任务。"""

    __tablename__ = "process_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("process_instance.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    task_type: Mapped[str] = mapped_column(String(16), default="TASK")
    lane: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    candidate_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # 结构化分派：角色编码与组织范围；candidate_role 保留展示文本
    candidate_role_code: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True, index=True
    )
    candidate_org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "org_unit.id",
            ondelete="SET NULL",
            name="fk_process_task_candidate_org_unit",
        ),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    row_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    assignee_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    form_data: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    claimed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    escalated_to_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_task_escalated_to",
        ),
        nullable=True,
    )
    escalated_to_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    completed_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    instance: Mapped["ProcessInstance"] = relationship("ProcessInstance", back_populates="tasks")
    events: Mapped[List["ProcessTaskEvent"]] = relationship(
        "ProcessTaskEvent",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="ProcessTaskEvent.id",
    )

    __table_args__ = (
        Index("ix_process_task_status_assignee", "status", "assignee_user_id"),
        Index("ix_process_task_instance_status", "instance_id", "status"),
        # 单令牌语义的数据库兜底：一个实例同一时刻最多一个 OPEN 任务。
        # 并行网关上线时需要删除这个索引，改为按令牌约束。
        Index(
            "uq_process_task_one_open",
            "instance_id",
            unique=True,
            postgresql_where=text("status IN ('PENDING','CLAIMED')"),
            sqlite_where=text("status IN ('PENDING','CLAIMED')"),
        ),
    )


class ProcessTaskEvent(Base):
    """任务生命周期事件，append-only。

    与审计日志的区别：审计日志面向「谁改了什么」，任务事件面向「这个任务经历了什么」，
    可以直接在任务详情里回放，不受其他业务日志淹没。
    """

    __tablename__ = "process_task_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_task.id",
            ondelete="CASCADE",
            name="fk_process_task_event_task",
        ),
        index=True,
    )
    instance_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_instance.id",
            ondelete="CASCADE",
            name="fk_process_task_event_instance",
        ),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    from_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_task_event_actor",
        ),
        nullable=True,
    )
    actor_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    task: Mapped["ProcessTask"] = relationship("ProcessTask", back_populates="events")

    __table_args__ = (Index("ix_process_task_event_task_created", "task_id", "created_at"),)


class IdempotencyRecord(Base):
    """写命令幂等记录。

    `(scope, key)` 唯一；请求先插入 PENDING 占位，成功后写回响应。
    并发重复请求会在唯一索引上排队，后到者读取首次结果。
    """

    __tablename__ = "idempotency_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(32), index=True)
    key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PENDING")
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("scope", "key", name="uq_idempotency_scope_key"),)


class FormDefinition(Base):
    """节点表单定义。

    `node_key=""` 表示该流程的默认表单；节点没有专属表单时回退到默认表单。
    字段结构是一个 JSON 数组，例如：
        [{"key":"approved","label":"是否通过","type":"select","required":true,
          "options":["是","否"]}]
    """

    __tablename__ = "form_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(128))
    fields: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint("process_id", "node_key", name="uq_form_definition_process_node"),
    )


class ProcessRule(Base):
    """节点分支规则。

    `conditions` 是条件列表（全部满足才命中），例如：
        [{"field":"approved","op":"eq","value":"是"}]
    命中后流转到 `target_node_key`。显式传入 next_node_key 时优先使用显式值。
    """

    __tablename__ = "process_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    conditions: Mapped[list] = mapped_column(JSON, default=list)
    target_node_key: Mapped[str] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_process_rule_process_node", "process_id", "node_key", "priority"),)


class ProcessExecutionConfig(Base):
    """流程级执行配置：默认任务时限与超期升级。"""

    __tablename__ = "process_execution_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), unique=True, index=True
    )
    # 新任务到期时间 = 创建时间 + 小时数；NULL 表示不设时限
    default_task_due_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 到期后再过多少小时升级；NULL 表示不自动升级
    default_escalation_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    default_escalation_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_process_execution_config_escalation_user",
        ),
        nullable=True,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    default_escalation_user: Mapped[Optional["User"]] = relationship("User")  # noqa: F821


class NodeAssignment(Base):
    """节点级分派配置：角色 / 组织 / 默认处理人 / 节点时限 / 升级。"""

    __tablename__ = "node_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey(
            "process_arch.id",
            ondelete="CASCADE",
            name="fk_node_assignment_process",
        ),
        index=True,
    )
    node_key: Mapped[str] = mapped_column(String(64))
    role: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # Role
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "org_unit.id",
            ondelete="SET NULL",
            name="fk_node_assignment_org_unit",
        ),
        nullable=True,
        index=True,
    )
    default_assignee_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_node_assignment_default_assignee",
        ),
        nullable=True,
        index=True,
    )
    due_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    escalation_hours: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    escalation_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_node_assignment_escalation_user",
        ),
        nullable=True,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    org_unit: Mapped[Optional["OrgUnit"]] = relationship("OrgUnit")  # noqa: F821
    default_assignee: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[default_assignee_user_id]
    )
    escalation_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[escalation_user_id]
    )

    __table_args__ = (
        UniqueConstraint("process_id", "node_key", name="uq_node_assignment_process_node"),
    )
