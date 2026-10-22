"""ERP / OA 集成：出站 Webhook 端点与 Outbox 投递记录。

采用 Outbox 模式：业务写操作只负责把事件写入 delivery 表，不阻塞请求；
由 `/integrations/deliveries/run` 统一投递，失败按次数退避重试。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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


class IntegrationEndpoint(Base):
    __tablename__ = "integration_endpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(16), default="WEBHOOK")  # WEBHOOK / ERP / OA
    url: Mapped[str] = mapped_column(String(500))
    secret: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    events: Mapped[list] = mapped_column(JSON, default=list)  # 空数组 = 订阅全部
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    deliveries: Mapped[List["IntegrationDelivery"]] = relationship(
        "IntegrationDelivery",
        back_populates="endpoint",
        cascade="all, delete-orphan",
    )


class IntegrationDelivery(Base):
    __tablename__ = "integration_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    endpoint_id: Mapped[int] = mapped_column(
        ForeignKey("integration_endpoint.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    response_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    endpoint: Mapped["IntegrationEndpoint"] = relationship(
        "IntegrationEndpoint", back_populates="deliveries"
    )

    __table_args__ = (
        Index("ix_integration_delivery_status_created", "status", "created_at"),
        Index("ix_integration_delivery_endpoint_created", "endpoint_id", "created_at"),
    )


class InboundWebhook(Base):
    """ERP/OA 反向调用入口。

    入站请求用 HMAC-SHA256 签名，服务账号决定操作人；`process_id` 非空时
    只能操作该流程，避免一个密钥横向启动所有流程。
    """

    __tablename__ = "inbound_webhook"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    secret: Mapped[str] = mapped_column(String(128))
    process_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_arch.id",
            ondelete="SET NULL",
            name="fk_inbound_webhook_process",
        ),
        nullable=True,
        index=True,
    )
    run_as_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "app_user.id",
            ondelete="SET NULL",
            name="fk_inbound_webhook_run_as",
        ),
        nullable=True,
        index=True,
    )
    actions: Mapped[list] = mapped_column(JSON, default=lambda: ["start_instance", "complete_task"])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_received_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    process: Mapped[Optional["ProcessArch"]] = relationship("ProcessArch")  # noqa: F821
    run_as_user: Mapped[Optional["User"]] = relationship("User")  # noqa: F821

    events: Mapped[List["InboundEvent"]] = relationship(
        "InboundEvent",
        back_populates="webhook",
        cascade="all, delete-orphan",
    )


class InboundEvent(Base):
    """已成功的入站事件，用于幂等与排障。

    只记录成功事件：失败请求不写记录，调用方可用同一个 event_id 重试。
    """

    __tablename__ = "inbound_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    webhook_id: Mapped[int] = mapped_column(
        ForeignKey("inbound_webhook.id", ondelete="CASCADE"), index=True
    )
    event_id: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="SUCCESS")
    instance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_instance.id",
            ondelete="SET NULL",
            name="fk_inbound_event_instance",
        ),
        nullable=True,
    )
    task_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "process_task.id",
            ondelete="SET NULL",
            name="fk_inbound_event_task",
        ),
        nullable=True,
    )
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)

    webhook: Mapped["InboundWebhook"] = relationship("InboundWebhook", back_populates="events")

    __table_args__ = (
        UniqueConstraint("webhook_id", "event_id", name="uq_inbound_event_webhook_event"),
        Index("ix_inbound_event_webhook_received", "webhook_id", "received_at"),
    )
