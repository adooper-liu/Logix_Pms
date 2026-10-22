"""步骤契约与交付物：定义 → 实例 → 版本。

分工（避免同一概念两套实现）：

- `WorkflowTemplate` 是给人读的方法手册：动作说明、关键要点、工具名清单；
- `StepContract` 是同一批步骤的可检查配置：结构化工具引用、验收标准、决策门；
- `DeliverableDefinition` 描述「这一步必须产出什么」，项目启动时实例化；
- `DeliverableVersion` 只追加不覆盖，实例上的 `current_version_id` 是当前指针。

文件二进制不落库：版本只记录元数据与 `file_ref`（外部位置，或后续存储层的对象键）。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
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


class StepContract(Base):
    """步骤契约：把「输入、工具、验收、责任人、决策门」变成可校验的配置。"""

    __tablename__ = "step_contract"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    step_no: Mapped[str] = mapped_column(
        ForeignKey("workflow_template.step_no", ondelete="CASCADE"), unique=True, index=True
    )

    inputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 上游交付物 / 数据 / 权限
    tool_codes: Mapped[Any] = mapped_column(JSON, default=list)  # 引用 Tool.code，不复制工具说明
    # {tool_code: REQUIRED | RECOMMENDED | OPTIONAL}；旧数据为空时按顺序推导
    tool_levels: Mapped[Any] = mapped_column(JSON, default=dict, nullable=True)
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # 角色，不是具体人
    decision_gate: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DeliverableDefinition(Base):
    """交付物定义：某一步必须产出什么。定义本身可编辑，实例创建后与定义解耦。"""

    __tablename__ = "deliverable_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    step_no: Mapped[str] = mapped_column(
        ForeignKey("workflow_template.step_no", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(16), default="DOCUMENT", index=True)
    required: Mapped[bool] = mapped_column(Boolean, default=True)
    template_ref: Mapped[Optional[str]] = mapped_column(
        String(200), nullable=True
    )  # 模板指引；模板库落地后改为外键
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_deliverable_definition_step", "step_no", "sort_order"),)


class DeliverableInstance(Base):
    """项目在某一步上的交付物实例。当前版本只是一个指针，恢复旧版不复制文件。"""

    __tablename__ = "deliverable_instance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    definition_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable_definition.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), index=True
    )
    project_step_id: Mapped[int] = mapped_column(
        ForeignKey("project_step.id", ondelete="CASCADE"), index=True
    )

    status: Mapped[str] = mapped_column(String(16), default="MISSING", index=True)
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 当前版本指针。刻意不加外键：instance ↔ version 互相引用会形成建表环，
    # SQLite 不支持后补外键，迁移链没法跨库。指针只由 deliverable 服务移动。
    current_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    definition: Mapped["DeliverableDefinition"] = relationship("DeliverableDefinition")
    project: Mapped["Project"] = relationship("Project")  # noqa: F821
    step: Mapped["ProjectStep"] = relationship(  # noqa: F821
        "ProjectStep", back_populates="deliverables"
    )
    versions: Mapped[List["DeliverableVersion"]] = relationship(
        "DeliverableVersion",
        back_populates="instance",
        cascade="all, delete-orphan",
        order_by="DeliverableVersion.version_no",
        foreign_keys="DeliverableVersion.instance_id",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_step_id", "definition_id", name="uq_deliverable_instance_step_definition"
        ),
    )


class DeliverableVersion(Base):
    """交付物版本：不可变内容 + 可变审批状态。修订号 R1、R2… 不给业务人员看 semver。"""

    __tablename__ = "deliverable_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("deliverable_instance.id", ondelete="CASCADE"), index=True
    )
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)

    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 版本说明

    # 文件元数据：二进制走统一存储层，数据库只存元数据与对象键
    file_ref: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True
    )  # 外部引用（共享盘/文档系统）
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # SHA-256
    storage_backend: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # local
    storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # 服务端生成

    author: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    author_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    reviewer: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reviewer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approver: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approver_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    base_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("deliverable_version.id", ondelete="SET NULL"), nullable=True
    )
    # 由哪个工具模板版本复制/生成而来；模板升级不影响已创建的版本
    source_template_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "tool_template_version.id",
            ondelete="SET NULL",
            name="fk_deliverable_version_source_template",
        ),
        nullable=True,
        index=True,
    )
    # 基于哪一版流程标准文件产出；与模板来源并列，不合并成一个字段
    source_document_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_document_version.id",
            ondelete="SET NULL",
            name="fk_deliverable_version_source_document",
        ),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    instance: Mapped["DeliverableInstance"] = relationship(
        "DeliverableInstance", back_populates="versions", foreign_keys=[instance_id]
    )
    source_document_version: Mapped[Optional["ProcessDocumentVersion"]] = relationship(  # noqa: F821
        "ProcessDocumentVersion", foreign_keys=[source_document_version_id]
    )

    __table_args__ = (
        UniqueConstraint("instance_id", "version_no", name="uq_deliverable_version_no"),
    )
