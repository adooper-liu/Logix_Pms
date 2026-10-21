"""用户与审计留痕。"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class User(Base):
    """系统用户。

    角色：
      ADMIN   系统管理员 —— 全部权限，含用户管理
      MANAGER 流程管理科 —— 全部业务写权限
      OWNER   流程 Owner —— 只能改自己名下的项目与流程模型
      VIEWER  只读
    """

    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(64))
    password_hash: Mapped[str] = mapped_column(String(255))

    role: Mapped[str] = mapped_column(String(16), index=True, default="VIEWER")
    department: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    audits: Mapped[List["AuditLog"]] = relationship("AuditLog", back_populates="user")


class AuditLog(Base):
    """写操作留痕。

    这是「闭环管理」类系统的硬需求：异常状态、项目进度、流程模型被谁改过，
    必须可追溯。只记录写操作，读操作不入库，避免日志淹没。
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True, index=True
    )
    username: Mapped[str] = mapped_column(String(64))  # 冗余存一份，用户删了也能追溯
    display_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    action: Mapped[str] = mapped_column(String(32), index=True)  # CREATE / UPDATE / DELETE
    entity_type: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="audits")

    __table_args__ = (Index("ix_audit_entity", "entity_type", "entity_id"),)
