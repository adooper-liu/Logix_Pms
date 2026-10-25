"""取消补偿：节点级补偿动作与实例补偿待办。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class CompensationAction(Base):
    """节点取消后的业务补偿动作（人工执行，系统留痕）。"""

    __tablename__ = "compensation_action"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE"), index=True
    )
    node_key: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint("process_id", "node_key", name="uq_compensation_action_process_node"),
    )


class CompensationRecord(Base):
    __tablename__ = "compensation_record"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("process_instance.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_task.id", ondelete="SET NULL"), nullable=True, index=True
    )
    node_key: Mapped[str] = mapped_column(String(64))
    action_name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", server_default="PENDING", index=True
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    completed_by_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    instance: Mapped["ProcessInstance"] = relationship("ProcessInstance")  # noqa: F821
    completed_by: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[completed_by_user_id]
    )

    __table_args__ = (Index("ix_compensation_record_instance_status", "instance_id", "status"),)
