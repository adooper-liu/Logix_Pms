"""同轮固定原引用及当时值，不是另一套改善阶段引擎。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class ProcessImprovementRound(Base):
    __tablename__ = "process_improvement_round"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("process_arch.id", ondelete="RESTRICT"), index=True
    )
    project_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("project.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    supersedes_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_improvement_round.id", ondelete="RESTRICT"), nullable=True
    )
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    name: Mapped[str] = mapped_column(String(160))
    scope_note: Mapped[str] = mapped_column(Text)
    asis_model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="RESTRICT", name="fk_round_asis"),
        nullable=True,
    )
    tobe_model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="RESTRICT", name="fk_round_tobe"),
        nullable=True,
    )
    released_model_version_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="RESTRICT", name="fk_round_released"),
        nullable=True,
    )
    metric_contracts: Mapped[list] = mapped_column(JSON, default=list)
    baseline_window: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_samples: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_window: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    after_samples: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    model_hashes: Mapped[dict] = mapped_column(JSON, default=dict)
    baseline_confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    baseline_confirmed_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    acceptance_locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    acceptance_locked_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
