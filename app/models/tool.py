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
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


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
