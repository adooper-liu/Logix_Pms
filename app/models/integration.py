"""ERP / OA 集成：出站 Webhook 端点与 Outbox 投递记录。

采用 Outbox 模式：业务写操作只负责把事件写入 delivery 表，不阻塞请求；
由 `/integrations/deliveries/run` 统一投递，失败按次数退避重试。
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
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
