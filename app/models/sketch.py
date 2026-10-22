"""架构草图：独立的 draw.io 白板，不参与 BPMN 建模与流程执行。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.timeutil import utcnow


class Sketch(Base):
    __tablename__ = "sketch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(128))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_arch.id",
            ondelete="SET NULL",
            name="fk_sketch_process",
        ),
        nullable=True,
        index=True,
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "project.id",
            ondelete="SET NULL",
            name="fk_sketch_project",
        ),
        nullable=True,
        index=True,
    )

    # draw.io embed 的 save 事件返回的 mxfile XML，原样保存
    mxfile_xml: Mapped[str] = mapped_column(Text, default="")

    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_sketch_created_by",
        ),
        nullable=True,
    )
    created_by_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, index=True
    )

    process: Mapped[Optional["ProcessArch"]] = relationship("ProcessArch")  # noqa: F821
    project: Mapped[Optional["Project"]] = relationship("Project")  # noqa: F821
