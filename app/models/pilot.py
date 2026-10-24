"""十层单页：流程试点路径、层状态、待办与异常改善卡。

一条试点路径 = 一条流程 + 10 个层状态。
层的“是否可退出”由现有 evidence 自动计算；待办和异常是人工维护的补充。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class PilotPath(Base):
    __tablename__ = "pilot_path"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_arch.id", ondelete="SET NULL", name="fk_pilot_path_process"),
        nullable=True,
        index=True,
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_pilot_path_owner"),
        nullable=True,
        index=True,
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="ACTIVE", server_default="ACTIVE", index=True
    )
    current_layer: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    baseline_version: Mapped[str] = mapped_column(String(16), default="V0.1", server_default="V0.1")
    draft_version: Mapped[str] = mapped_column(String(16), default="V0.1", server_default="V0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class PilotLayer(Base):
    __tablename__ = "pilot_layer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_path.id", ondelete="CASCADE", name="fk_pilot_layer_path"),
        index=True,
    )
    layer_no: Mapped[int] = mapped_column(Integer, index=True)
    context_summary: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (UniqueConstraint("path_id", "layer_no", name="uq_pilot_layer_path_no"),)


class PilotTask(Base):
    __tablename__ = "pilot_task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_path.id", ondelete="CASCADE", name="fk_pilot_task_path"),
        index=True,
    )
    layer_no: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    priority: Mapped[str] = mapped_column(
        String(16), default="MEDIUM", server_default="MEDIUM", index=True
    )
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_pilot_task_owner"),
        nullable=True,
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    acceptance: Mapped[Optional[str]] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="TODO", server_default="TODO", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class PilotIssue(Base):
    __tablename__ = "pilot_issue"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    path_id: Mapped[int] = mapped_column(
        ForeignKey("pilot_path.id", ondelete="CASCADE", name="fk_pilot_issue_path"),
        index=True,
    )
    layer_no: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    severity: Mapped[str] = mapped_column(
        String(16), default="MAJOR", server_default="MAJOR", index=True
    )
    workaround: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    verification: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    owner_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_pilot_issue_owner"),
        nullable=True,
    )
    owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="OPEN", server_default="OPEN", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
