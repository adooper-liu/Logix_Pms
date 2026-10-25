"""L5 任务定义：L4 活动下的可执行任务，可挂标准工时。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
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


class ProcessTaskDefinition(Base):
    __tablename__ = "process_task_definition"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="CASCADE", name="fk_task_activity"),
        index=True,
    )
    code: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    position_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("position.id", ondelete="SET NULL", name="fk_task_position"),
        nullable=True,
        index=True,
    )
    standard_minutes: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    frequency: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    activity: Mapped["ProcessArch"] = relationship(  # noqa: F821
        "ProcessArch", back_populates="task_definitions"
    )
    position: Mapped[Optional["Position"]] = relationship("Position")  # noqa: F821

    __table_args__ = (
        UniqueConstraint("activity_id", "code", name="uq_process_task_activity_code"),
        Index("ix_process_task_activity_sort", "activity_id", "sort_order"),
    )
