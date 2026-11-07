"""Thin engine mappings and durable delivery identity; not a second workflow store."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.timeutil import utcnow


class EngineDeployment(Base):
    __tablename__ = "engine_deployment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("process_model_version.id", ondelete="RESTRICT")
    )
    namespace: Mapped[str] = mapped_column(String(64))
    xml_hash: Mapped[str] = mapped_column(String(64))
    basis_hash: Mapped[str] = mapped_column(String(64))
    definition_id: Mapped[str] = mapped_column(String(128))
    deployment_id: Mapped[str] = mapped_column(String(128))
    execution_hash: Mapped[str] = mapped_column(String(64))
    command_id: Mapped[str] = mapped_column(String(36))
    configuration: Mapped[dict] = mapped_column(JSON)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "namespace",
            "model_version_id",
            "xml_hash",
            "basis_hash",
            name="uq_engine_deployment_basis",
        ),
    )


class EngineCommand(Base):
    __tablename__ = "engine_command"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    namespace: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    action: Mapped[str] = mapped_column(String(32))
    target: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    request: Mapped[dict] = mapped_column(JSON)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    lock_key: Mapped[Optional[str]] = mapped_column(String(180), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="PREPARED")
    receipt: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    instance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_instance.id", ondelete="RESTRICT"), nullable=True
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("process_task.id", ondelete="RESTRICT"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    __table_args__ = (
        UniqueConstraint(
            "namespace", "user_id", "idempotency_key", name="uq_engine_command_client_key"
        ),
    )


class EngineInbox(Base):
    __tablename__ = "engine_inbox"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    namespace: Mapped[str] = mapped_column(String(64))
    event_id: Mapped[str] = mapped_column(String(36))
    journal_id: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (UniqueConstraint("namespace", "event_id", name="uq_engine_inbox_event"),)


class EngineCursor(Base):
    __tablename__ = "engine_cursor"

    namespace: Mapped[str] = mapped_column(String(64), primary_key=True)
    after_id: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
