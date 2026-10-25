"""方法论工具箱模型。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional

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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class Tool(Base):
    """一个可落地的流程工具，含标准操作步骤与决策信息。"""

    __tablename__ = "tool"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64), index=True)
    alias: Mapped[Optional[str]] = mapped_column(String(96), nullable=True)  # 英文名/别名

    category: Mapped[str] = mapped_column(
        String(16), index=True
    )  # DIAGNOSE / DESIGN / DEPLOY / MONITOR
    stage_no: Mapped[int] = mapped_column(Integer, index=True)  # 主要适用阶段 1–5

    purpose: Mapped[str] = mapped_column(Text)  # 解决什么问题
    when_to_use: Mapped[str] = mapped_column(Text)  # 什么场景选它
    steps: Mapped[Any] = mapped_column(JSON)  # ["步骤1", ...] 5 步
    template_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 模板/表格指引
    pitfalls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 常见误用

    # ---- 问题驱动的决策字段 ----
    not_applicable_when: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prerequisites: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification_standard: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    difficulty: Mapped[str] = mapped_column(
        String(8), default="MEDIUM", server_default="MEDIUM", index=True
    )  # LOW / MEDIUM / HIGH
    typical_duration: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_tool_owner_user"),
        nullable=True,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(
        String(16), default="PUBLISHED", server_default="PUBLISHED", index=True
    )  # DRAFT / IN_REVIEW / PUBLISHED / VERIFIED / ARCHIVED
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    reviewed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_tool_reviewed_by_user"),
        nullable=True,
        index=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    review_due_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )

    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    scenario_rows: Mapped[List["ToolScenarioLink"]] = relationship(
        "ToolScenarioLink",
        back_populates="tool",
        cascade="all, delete-orphan",
        order_by="ToolScenarioLink.id",
    )
    owner_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[owner_user_id]
    )
    reviewed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[reviewed_by_user_id]
    )
    usage_rows: Mapped[List["ToolUsage"]] = relationship(
        "ToolUsage",
        back_populates="tool",
        cascade="all, delete-orphan",
        order_by="ToolUsage.id",
    )
    plan_rows: Mapped[List["ToolUsagePlan"]] = relationship(
        "ToolUsagePlan",
        back_populates="tool",
        cascade="all, delete-orphan",
        order_by="ToolUsagePlan.id",
    )

    @property
    def scenario_codes(self) -> List[str]:
        return [row.scenario.code for row in self.scenario_rows if row.scenario]

    @property
    def scenario_names(self) -> List[str]:
        return [row.scenario.name for row in self.scenario_rows if row.scenario]

    @property
    def difficulty_label(self) -> str:
        return {"LOW": "低", "MEDIUM": "中", "HIGH": "高"}.get(self.difficulty, self.difficulty)

    @property
    def category_label(self) -> str:
        return {
            "DIAGNOSE": "诊断工具",
            "DESIGN": "设计工具",
            "DEPLOY": "落地工具",
            "MONITOR": "监控工具",
        }.get(self.category, self.category)

    @property
    def owner(self) -> Optional[str]:
        return self.owner_user.display_name if self.owner_user else None

    @property
    def status_label(self) -> str:
        return {
            "DRAFT": "草稿",
            "IN_REVIEW": "待审核",
            "PUBLISHED": "已发布",
            "VERIFIED": "已验证",
            "ARCHIVED": "已归档",
        }.get(self.status, self.status)

    @property
    def review_overdue(self) -> bool:
        """启用中的工具过了复核日期；停用工具不再提醒。"""
        return bool(
            self.is_active and self.review_due_at is not None and self.review_due_at < date.today()
        )


class ToolScenarioLink(Base):
    """工具 ↔ 痛点场景。复用 knowledge_scenario 字典，不另建一套分类。"""

    __tablename__ = "tool_scenario_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_id: Mapped[int] = mapped_column(ForeignKey("tool.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_scenario.id", ondelete="CASCADE"), index=True
    )
    weight: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")

    tool: Mapped["Tool"] = relationship("Tool", back_populates="scenario_rows")
    scenario: Mapped["KnowledgeScenario"] = relationship(  # noqa: F821
        "KnowledgeScenario"
    )

    __table_args__ = (UniqueConstraint("tool_id", "scenario_id", name="uq_tool_scenario_link"),)


class ToolUsage(Base):
    """工具的现场使用证据。

    与知识条目的 `knowledge_usage` 分开：知识证据回答「这条参考有没有用」，
    工具证据回答「这个工具在某个步骤有没有用」；工具详情把两者聚合展示。
    """

    __tablename__ = "tool_usage"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_code: Mapped[str] = mapped_column(ForeignKey("tool.code", ondelete="CASCADE"), index=True)
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

    tool: Mapped["Tool"] = relationship("Tool", back_populates="usage_rows")
    used_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[used_by_user_id]
    )

    __table_args__ = (Index("ix_tool_usage_code_time", "tool_code", "used_at"),)


class ToolUsagePlan(Base):
    """工具使用计划：在项目/步骤上下文中计划使用某个工具，执行后再回填状态。"""

    __tablename__ = "tool_usage_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_code: Mapped[str] = mapped_column(ForeignKey("tool.code", ondelete="CASCADE"), index=True)
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), nullable=True, index=True
    )
    step_no: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    planned_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    planned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default="PLANNED", server_default="PLANNED", index=True
    )  # PLANNED / IN_PROGRESS / DONE / CANCELLED
    target: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    tool: Mapped["Tool"] = relationship("Tool", back_populates="plan_rows")
    planned_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[planned_by_user_id]
    )

    __table_args__ = (Index("ix_tool_usage_plan_tool_time", "tool_code", "planned_at"),)
