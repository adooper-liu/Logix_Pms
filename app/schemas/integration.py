"""ERP / OA 集成的出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class IntegrationEndpointCreate(BaseModel):
    code: str = Field(max_length=32)
    name: str = Field(max_length=120)
    kind: str = Field(default="WEBHOOK", description="WEBHOOK / ERP / OA")
    url: str = Field(max_length=500)
    secret: Optional[str] = Field(default=None, max_length=128, description="用于 HMAC 签名")
    events: List[str] = Field(default_factory=list, description="空数组表示订阅全部事件")
    is_active: bool = True


class IntegrationEndpointUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    kind: Optional[str] = None
    url: Optional[str] = Field(default=None, max_length=500)
    secret: Optional[str] = Field(default=None, max_length=128)
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class IntegrationEndpointOut(BaseModel):
    id: int
    code: str
    name: str
    kind: str
    url: str
    has_secret: bool = False
    events: List[str] = []
    is_active: bool = True
    updated_at: Optional[UtcDateTime] = None


class IntegrationDeliveryOut(BaseModel):
    id: int
    endpoint_id: int
    endpoint_code: str
    endpoint_name: str
    event_type: str
    payload: Dict = {}
    status: str
    status_label: str
    attempts: int
    response_code: Optional[int] = None
    error: Optional[str] = None
    next_attempt_at: Optional[UtcDateTime] = None
    created_at: UtcDateTime
    delivered_at: Optional[UtcDateTime] = None


class DeliveryRunResult(BaseModel):
    processed: int = 0
    delivered: int = 0
    failed: int = 0
    pending: int = 0
