"""启动路径的人工跳过记录。

只表达一件事：某个步骤本轮不把现有数据作为“就绪证据”。
它不修改任何业务表，也不参与 24 步/9 阶段项目的步骤状态。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class StartupStepSkip(Base):
    __tablename__ = "startup_step_skip"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 全局一步一条：启动路径是全公司口径，不按用户各自维护一套就绪度
    step_key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    skipped_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_startup_step_skip_user"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class StartupPilotConfirm(Base):
    """首次上线确认：把“数据看起来齐了”升级为一次可审计的上线动作。"""

    __tablename__ = "startup_pilot_confirm"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 单行里程碑；保留 key 以便未来扩展其他里程碑
    key: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    confirmed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL", name="fk_startup_pilot_confirm_user"),
        nullable=True,
        index=True,
    )
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
