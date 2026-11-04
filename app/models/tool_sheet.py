"""填过的工具模板：挂在一条流程上，可同时写成战略目标。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ToolSheet(Base):
    __tablename__ = "tool_sheet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_code: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tool.code", ondelete="CASCADE", name="fk_tool_sheet_tool"),
        index=True,
    )
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_tool_sheet_process"),
        index=True,
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL", name="fk_tool_sheet_project"),
        nullable=True,
        index=True,
    )
    objective_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "strategy_objective.id",
            ondelete="SET NULL",
            name="fk_tool_sheet_objective",
        ),
        nullable=True,
        index=True,
    )
    step_no: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    template_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "tool_template_version.id", ondelete="RESTRICT", name="fk_sheet_template_version"
        ),
        nullable=True,
    )
    handoff: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    title: Mapped[str] = mapped_column(String(160))
    fields: Mapped[Any] = mapped_column(JSON, default=list)
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_tool_sheet_user"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_tool_sheet_process_tool", "process_id", "tool_code"),)
