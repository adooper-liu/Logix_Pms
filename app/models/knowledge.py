"""流程知识库模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import (
    Boolean,
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


class KnowledgeItem(Base):
    """案例 / 模板 / 方法 / 工具指南。

    知识库只放「可参考、可改编」的内容。强制执行的制度走 `process_document`，
    工具定义走 `tool` 表；这里通过 `tool_code` 建立引用，不复制定义。
    """

    __tablename__ = "knowledge_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    type: Mapped[str] = mapped_column(
        String(16), index=True
    )  # CASE / TEMPLATE / METHOD / TOOL；旧值 BEST_PRACTICE / STANDARD 兼容
    methodology: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)

    summary: Mapped[str] = mapped_column(String(400))
    content: Mapped[str] = mapped_column(Text)

    # ---- 求真审核与固定字段 ----
    # DRAFT → IN_REVIEW → PUBLISHED / VERIFIED → ARCHIVED
    status: Mapped[str] = mapped_column(
        String(16), default="PUBLISHED", server_default="PUBLISHED", index=True
    )
    claim: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    applicable_when: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    not_applicable_when: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    input_conditions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    steps_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    outputs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")

    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_knowledge_owner_user"),
        nullable=True,
        index=True,
    )
    verified_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_knowledge_verified_by"),
        nullable=True,
        index=True,
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_due_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_best_practice: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # 关联对象，便于“从项目沉淀到知识库”
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL"), nullable=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True
    )
    tool_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)

    author: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=True
    )

    tag_rows: Mapped[List["KnowledgeTag"]] = relationship(
        "KnowledgeTag",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="KnowledgeTag.id",
    )
    scenario_rows: Mapped[List["KnowledgeScenarioLink"]] = relationship(
        "KnowledgeScenarioLink",
        back_populates="item",
        cascade="all, delete-orphan",
    )
    workflow_links: Mapped[List["KnowledgeWorkflowLink"]] = relationship(
        "KnowledgeWorkflowLink",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="KnowledgeWorkflowLink.id",
    )
    usage_rows: Mapped[List["KnowledgeUsage"]] = relationship(
        "KnowledgeUsage",
        back_populates="item",
        cascade="all, delete-orphan",
    )

    owner_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[owner_user_id]
    )
    verified_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[verified_by_user_id]
    )

    @property
    def tags(self) -> List[str]:
        """标签以关联表为唯一事实来源，这里只是给序列化用的投影。"""
        return [t.tag for t in self.tag_rows]

    @property
    def scenario_codes(self) -> List[str]:
        return [row.scenario.code for row in self.scenario_rows if row.scenario]

    @property
    def scenario_names(self) -> List[str]:
        return [row.scenario.name for row in self.scenario_rows if row.scenario]

    @property
    def owner(self) -> Optional[str]:
        return self.author

    @property
    def stage_nos(self) -> List[int]:
        return sorted({row.stage_no for row in self.workflow_links})

    @property
    def step_nos(self) -> List[str]:
        return sorted({row.step_no for row in self.workflow_links if row.step_no})


class KnowledgeTag(Base):
    """知识条目的标签。

    刻意做成关联表而不是 JSON 列：JSON 的包含查询在不同数据库上行为不一致，
    之前的实现被迫在「取出分页结果之后」在内存里过滤，导致筛选结果和 total
    都会随 page_size 变化。规范化之后，筛选和计数都回到 SQL 层，跨库也一致。
    """

    __tablename__ = "knowledge_tag"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_item.id", ondelete="CASCADE"), index=True
    )
    tag: Mapped[str] = mapped_column(String(32), index=True)

    item: Mapped["KnowledgeItem"] = relationship("KnowledgeItem", back_populates="tag_rows")

    __table_args__ = (Index("ix_knowledge_tag_item_tag", "knowledge_id", "tag", unique=True),)


class KnowledgeScenario(Base):
    """场景字典：用户带着什么问题来，而不是文件属于什么类型。"""

    __tablename__ = "knowledge_scenario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")

    links: Mapped[List["KnowledgeScenarioLink"]] = relationship(
        "KnowledgeScenarioLink", back_populates="scenario", cascade="all, delete-orphan"
    )


class KnowledgeScenarioLink(Base):
    __tablename__ = "knowledge_scenario_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_item.id", ondelete="CASCADE"), index=True
    )
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_scenario.id", ondelete="CASCADE"), index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")

    item: Mapped["KnowledgeItem"] = relationship("KnowledgeItem", back_populates="scenario_rows")
    scenario: Mapped["KnowledgeScenario"] = relationship(
        "KnowledgeScenario", back_populates="links"
    )

    __table_args__ = (
        UniqueConstraint("knowledge_id", "scenario_id", name="uq_knowledge_scenario_link"),
    )


class KnowledgeWorkflowLink(Base):
    """知识 → 五阶段/步骤的推荐关系。step_no 为空串表示阶段级推荐。"""

    __tablename__ = "knowledge_workflow_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_item.id", ondelete="CASCADE"), index=True
    )
    stage_no: Mapped[int] = mapped_column(Integer, index=True)
    step_no: Mapped[str] = mapped_column(String(8), default="", index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")

    item: Mapped["KnowledgeItem"] = relationship("KnowledgeItem", back_populates="workflow_links")

    __table_args__ = (
        UniqueConstraint("knowledge_id", "stage_no", "step_no", name="uq_knowledge_workflow_link"),
    )


class KnowledgeUsage(Base):
    """使用证据：谁在哪个项目/步骤用过，效果如何。"""

    __tablename__ = "knowledge_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_item.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_no: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    used_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    used_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    outcome: Mapped[str] = mapped_column(
        String(16), default="EFFECTIVE", server_default="EFFECTIVE", index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    item: Mapped["KnowledgeItem"] = relationship("KnowledgeItem", back_populates="usage_rows")
    used_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[used_by_user_id]
    )

    __table_args__ = (Index("ix_knowledge_usage_item_time", "knowledge_id", "used_at"),)
