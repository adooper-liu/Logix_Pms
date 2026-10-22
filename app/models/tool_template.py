"""工具预制模板：工具 → 模板（按格式/场景）→ 模板版本 → 使用记录。

模板是方法落到交付物的载体，不是交付物本身：
- 模板版本不可变，`current_version_id` 只是指针；
- 调用模板会写 `template_usage`；复制到项目会另建交付物版本并固定来源版本；
- 集团/分公司变体与覆盖策略属于后续阶段，这里不做。
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


class ToolTemplate(Base):
    """某个工具下的一套预制模板（同工具同格式可以有多个，但只有一个默认）。"""

    __tablename__ = "tool_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_code: Mapped[str] = mapped_column(ForeignKey("tool.code", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    format: Mapped[str] = mapped_column(String(16), index=True)  # TemplateFormat
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 这个模板产出哪类交付物；为空表示不限
    deliverable_definition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("deliverable_definition.id", ondelete="SET NULL"), nullable=True, index=True
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # NULL = 集团通用；非空 = 该组织及其下级可见
    org_unit_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("org_unit.id", ondelete="SET NULL", name="fk_tool_template_org_unit"),
        nullable=True,
        index=True,
    )
    review_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 复审日期

    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # 与版本表形成指针；刻意不加外键，理由同 deliverable_instance
    current_version_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    versions: Mapped[List["ToolTemplateVersion"]] = relationship(
        "ToolTemplateVersion",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="ToolTemplateVersion.id",
    )
    tool: Mapped["Tool"] = relationship("Tool")  # noqa: F821
    definition: Mapped[Optional["DeliverableDefinition"]] = relationship(  # noqa: F821
        "DeliverableDefinition"
    )
    org_unit: Mapped[Optional["OrgUnit"]] = relationship("OrgUnit")  # noqa: F821

    __table_args__ = (Index("ix_tool_template_tool_format", "tool_code", "format"),)


class ToolTemplateVersion(Base):
    """模板版本：语义化版本号 + 不可变文件 + 占位符定义。"""

    __tablename__ = "tool_template_version"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("tool_template.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(20))  # major.minor.patch
    status: Mapped[str] = mapped_column(String(16), default="DRAFT", index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    storage_backend: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    storage_key: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # [{"key","label","source","required","format"}]；source 由服务端上下文解析
    placeholders: Mapped[Any] = mapped_column(JSON, default=list)

    base_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("tool_template_version.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approved_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    valid_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    valid_to: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    template: Mapped["ToolTemplate"] = relationship("ToolTemplate", back_populates="versions")

    __table_args__ = (
        UniqueConstraint("template_id", "version_label", name="uq_tool_template_version_label"),
    )


class TemplateUsage(Base):
    """谁在哪个项目/步骤用了哪个模板版本，是否复制成了交付物。"""

    __tablename__ = "template_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("tool_template.id", ondelete="CASCADE"), index=True
    )
    template_version_id: Mapped[int] = mapped_column(
        ForeignKey("tool_template_version.id", ondelete="CASCADE"), index=True
    )
    mode: Mapped[str] = mapped_column(String(16), index=True)  # TemplateMode

    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deliverable_instance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("deliverable_instance.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deliverable_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("deliverable_version.id", ondelete="SET NULL"), nullable=True
    )
    context_json: Mapped[Any] = mapped_column(JSON, default=dict)

    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    template_version: Mapped["ToolTemplateVersion"] = relationship("ToolTemplateVersion")
    project: Mapped[Optional["Project"]] = relationship("Project")  # noqa: F821
