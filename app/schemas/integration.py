"""ERP / OA 集成的出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime, UtcDateTimeIn


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


# ---------------------------------------------------------------- 入站 Webhook


class InboundWebhookCreate(BaseModel):
    code: str = Field(max_length=32, description="调用路径 /integrations/inbound/{code}")
    name: str = Field(max_length=120)
    process_id: Optional[int] = Field(
        default=None, description="限定流程；null 表示按请求里的 process_id"
    )
    run_as_user_id: int = Field(description="执行入站操作的服务账号（MANAGER/ADMIN）")
    actions: List[str] = Field(
        default_factory=lambda: ["start_instance", "complete_task"],
        description="允许的动作：start_instance / complete_task",
    )
    is_active: bool = True


class InboundWebhookUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    process_id: Optional[int] = None
    run_as_user_id: Optional[int] = None
    actions: Optional[List[str]] = None
    is_active: Optional[bool] = None
    rotate_secret: bool = Field(default=False, description="true 时生成新密钥并在响应中返回")


class InboundWebhookOut(BaseModel):
    id: int
    code: str
    name: str
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    run_as_user_id: Optional[int] = None
    run_as_user_name: Optional[str] = None
    actions: List[str] = []
    action_labels: List[str] = []
    is_active: bool = True
    inbound_path: str = ""
    last_received_at: Optional[UtcDateTime] = None
    created_at: UtcDateTime
    updated_at: Optional[UtcDateTime] = None


class InboundWebhookCreatedOut(InboundWebhookOut):
    secret: Optional[str] = Field(default=None, description="仅创建/轮换时返回一次")


class InboundRequest(BaseModel):
    event_id: str = Field(max_length=128, description="调用方事件 id，用于幂等")
    action: str = Field(
        max_length=32, description="start_instance / complete_task / record_worklog"
    )
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    variables: Optional[Dict] = None
    assignments: Optional[Dict[str, int]] = None
    task_id: Optional[int] = None
    form_data: Optional[Dict] = None
    next_node_key: Optional[str] = Field(default=None, max_length=64)
    comment: Optional[str] = None

    # record_worklog：MES/HR/OA 回传实际工时
    effort_minutes: Optional[float] = Field(default=None, ge=0, le=10080)
    work_type: Optional[str] = Field(default=None, max_length=16)
    started_at: Optional[UtcDateTimeIn] = None
    ended_at: Optional[UtcDateTimeIn] = None

    # record_kpi：ERP/MES/BI 回传指标数据点
    kpi_id: Optional[int] = None
    period: Optional[date] = None
    value: Optional[float] = None


class InboundResult(BaseModel):
    status: str = "ok"
    action: str
    duplicate: bool = False
    instance_id: Optional[int] = None
    instance_code: Optional[str] = None
    task_id: Optional[int] = None
    task_status: Optional[str] = None
    message: Optional[str] = None


class InboundEventOut(BaseModel):
    id: int
    event_id: str
    action: str
    status: str
    instance_id: Optional[int] = None
    task_id: Optional[int] = None
    error: Optional[str] = None
    received_at: UtcDateTime
