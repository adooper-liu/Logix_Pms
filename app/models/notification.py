"""站内通知。

通知只做「提醒」，不承载业务状态；真正的状态仍在任务/实例/异常表里。
去重策略：同一用户、同一类型、同一实体只保留一条未读通知。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    link: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_notification_user_read", "user_id", "is_read", "created_at"),
        Index("ix_notification_entity", "entity_type", "entity_id"),
    )
