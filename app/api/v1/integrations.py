"""ERP / OA 集成：Webhook 端点管理、Outbox 投递与重试。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from sqlalchemy import select

from app.api.deps import DbSession, ManagerUser
from app.models.integration import (
    InboundEvent,
    InboundWebhook,
    IntegrationDelivery,
    IntegrationEndpoint,
)
from app.models.process import ProcessArch
from app.schemas.common import DeleteResult
from app.schemas.integration import (
    DeliveryRunResult,
    InboundEventOut,
    InboundResult,
    InboundWebhookCreate,
    InboundWebhookCreatedOut,
    InboundWebhookOut,
    InboundWebhookUpdate,
    IntegrationDeliveryOut,
    IntegrationEndpointCreate,
    IntegrationEndpointOut,
    IntegrationEndpointUpdate,
)
from app.services import audit as audit_service
from app.services import inbound as inbound_service
from app.services import integrations as integration_service

router = APIRouter(prefix="/integrations", tags=["集成"])
# 入站端点不挂登录依赖：调用方是 ERP/OA，用 HMAC 签名鉴权
inbound_router = APIRouter(prefix="/integrations/inbound", tags=["集成"])


@router.get("/events", summary="可订阅的事件类型")
def list_events():
    return [
        {"event": event, "label": label}
        for event, label in integration_service.EVENT_LABELS.items()
    ]


@router.get("/endpoints", response_model=List[IntegrationEndpointOut], summary="集成端点列表")
def list_endpoints(db: DbSession):
    rows = db.scalars(select(IntegrationEndpoint).order_by(IntegrationEndpoint.id)).all()
    return [integration_service.endpoint_out(row) for row in rows]


@router.post(
    "/endpoints",
    response_model=IntegrationEndpointOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增集成端点（MANAGER+）",
)
def create_endpoint(payload: IntegrationEndpointCreate, db: DbSession, user: ManagerUser):
    if db.scalar(select(IntegrationEndpoint).where(IntegrationEndpoint.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"端点编码 {payload.code} 已存在")
    url = integration_service.validate_url(payload.url)
    events = integration_service.validate_events(payload.events)
    endpoint = IntegrationEndpoint(
        code=payload.code,
        name=payload.name,
        kind=payload.kind,
        url=url,
        secret=payload.secret,
        events=events,
        is_active=payload.is_active,
    )
    db.add(endpoint)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "integration_endpoint",
        endpoint.id,
        f"新增集成端点 {endpoint.code} → {endpoint.url}",
    )
    db.commit()
    db.refresh(endpoint)
    return integration_service.endpoint_out(endpoint)


@router.patch(
    "/endpoints/{endpoint_id}",
    response_model=IntegrationEndpointOut,
    summary="修改集成端点（MANAGER+）",
)
def update_endpoint(
    endpoint_id: int,
    payload: IntegrationEndpointUpdate,
    db: DbSession,
    user: ManagerUser,
):
    endpoint = db.get(IntegrationEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="集成端点不存在")
    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"] is not None:
        data["url"] = integration_service.validate_url(data["url"])
    if "events" in data and data["events"] is not None:
        data["events"] = integration_service.validate_events(data["events"])
    for key, value in data.items():
        setattr(endpoint, key, value)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "integration_endpoint",
        endpoint.id,
        f"修改集成端点 {endpoint.code}",
    )
    db.commit()
    db.refresh(endpoint)
    return integration_service.endpoint_out(endpoint)


@router.delete(
    "/endpoints/{endpoint_id}",
    response_model=DeleteResult,
    summary="删除集成端点及其投递记录（MANAGER+）",
)
def delete_endpoint(endpoint_id: int, db: DbSession, user: ManagerUser):
    endpoint = db.get(IntegrationEndpoint, endpoint_id)
    if endpoint is None:
        raise HTTPException(status_code=404, detail="集成端点不存在")
    code = endpoint.code
    audit_service.record(
        db, user, "DELETE", "integration_endpoint", endpoint.id, f"删除集成端点 {code}"
    )
    db.delete(endpoint)
    db.commit()
    return DeleteResult(deleted=1)


@router.get(
    "/deliveries",
    response_model=List[IntegrationDeliveryOut],
    summary="投递记录",
)
def list_deliveries(
    db: DbSession,
    status_: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
):
    stmt = select(IntegrationDelivery)
    if status_:
        stmt = stmt.where(IntegrationDelivery.status == status_)
    rows = db.scalars(
        stmt.order_by(IntegrationDelivery.created_at.desc(), IntegrationDelivery.id.desc()).limit(
            limit
        )
    ).all()
    return [integration_service.delivery_out(row) for row in rows]


@router.post(
    "/deliveries/run",
    response_model=DeliveryRunResult,
    summary="投递待发送事件（MANAGER+）",
)
def run_deliveries(
    db: DbSession,
    user: ManagerUser,
    limit: int = Query(default=50, ge=1, le=200),
):
    result = integration_service.deliver_pending(db, limit=limit)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "integration_delivery",
        None,
        f"投递集成事件：处理 {result.processed}、成功 {result.delivered}、"
        f"失败 {result.failed}、待发送 {result.pending}",
    )
    db.commit()
    return result


@router.post(
    "/deliveries/{delivery_id}/retry",
    response_model=IntegrationDeliveryOut,
    summary="重试某条投递（MANAGER+）",
)
def retry_delivery(delivery_id: int, db: DbSession, user: ManagerUser):
    delivery = db.get(IntegrationDelivery, delivery_id)
    if delivery is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    integration_service.retry_delivery(db, delivery)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "integration_delivery",
        delivery.id,
        f"重试投递 #{delivery.id}（{delivery.event_type}）",
    )
    db.commit()
    db.refresh(delivery)
    return integration_service.delivery_out(delivery)


# ---------------------------------------------------------------- 入站 Webhook


@inbound_router.post(
    "/{code}",
    response_model=InboundResult,
    summary="接收入站 Webhook（HMAC-SHA256）",
)
async def receive_inbound(
    code: str,
    request: Request,
    db: DbSession,
    x_logix_timestamp: Optional[str] = Header(
        default=None, alias="X-Logix-Timestamp", description="Unix 秒"
    ),
    x_logix_signature: Optional[str] = Header(
        default=None, alias="X-Logix-Signature", description="sha256=<hex>"
    ),
):
    raw_body = await request.body()
    return inbound_service.receive(db, code, raw_body, x_logix_timestamp, x_logix_signature)


@router.get(
    "/inbound-actions",
    summary="可用的入站动作（MANAGER+）",
)
def list_inbound_actions(user: ManagerUser):
    return [{"value": action, "label": label} for action, label in inbound_service.ACTIONS.items()]


@router.get(
    "/inbound-hooks",
    response_model=List[InboundWebhookOut],
    summary="入站 Webhook 列表（MANAGER+）",
)
def list_inbound_hooks(db: DbSession, user: ManagerUser):
    rows = db.scalars(select(InboundWebhook).order_by(InboundWebhook.id)).all()
    return [inbound_service.hook_out(row) for row in rows]


@router.post(
    "/inbound-hooks",
    response_model=InboundWebhookCreatedOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建入站 Webhook（MANAGER+，密钥只返回一次）",
)
def create_inbound_hook(payload: InboundWebhookCreate, db: DbSession, user: ManagerUser):
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="编码不能为空")
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="名称不能为空")
    if db.scalar(select(InboundWebhook).where(InboundWebhook.code == code)):
        raise HTTPException(status_code=409, detail=f"入站 Webhook 编码 {code} 已存在")
    if payload.process_id is not None and db.get(ProcessArch, payload.process_id) is None:
        raise HTTPException(status_code=400, detail="process_id 指向的流程不存在")
    if (
        payload.process_id is not None
        and payload.actions
        and ("start_instance" not in payload.actions)
    ):
        raise HTTPException(
            status_code=400,
            detail="限定流程的入站 Webhook 必须允许 start_instance",
        )
    inbound_service.validate_run_as(db, payload.run_as_user_id)
    actions = inbound_service.validate_actions(payload.actions)
    secret = inbound_service.generate_secret()
    hook = InboundWebhook(
        code=code,
        name=name,
        secret=secret,
        process_id=payload.process_id,
        run_as_user_id=payload.run_as_user_id,
        actions=actions,
        is_active=payload.is_active,
    )
    db.add(hook)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "inbound_webhook",
        hook.id,
        f"新建入站 Webhook {hook.code}（服务账号 #{payload.run_as_user_id}）",
    )
    db.commit()
    db.refresh(hook)
    return inbound_service.hook_out(hook, secret)


@router.patch(
    "/inbound-hooks/{hook_id}",
    response_model=InboundWebhookCreatedOut,
    summary="修改入站 Webhook / 轮换密钥（MANAGER+）",
)
def update_inbound_hook(
    hook_id: int,
    payload: InboundWebhookUpdate,
    db: DbSession,
    user: ManagerUser,
):
    hook = db.get(InboundWebhook, hook_id)
    if hook is None:
        raise HTTPException(status_code=404, detail="入站 Webhook 不存在")
    data = payload.model_dump(exclude_unset=True)
    rotate = bool(data.pop("rotate_secret", False))
    if "process_id" in data and data["process_id"] is not None:
        if db.get(ProcessArch, data["process_id"]) is None:
            raise HTTPException(status_code=400, detail="process_id 指向的流程不存在")
    if "name" in data and not (data["name"] or "").strip():
        raise HTTPException(status_code=400, detail="名称不能为空")
    if "run_as_user_id" in data:
        if data["run_as_user_id"] is None:
            raise HTTPException(status_code=400, detail="必须配置入站服务账号")
        inbound_service.validate_run_as(db, data["run_as_user_id"])
    if "actions" in data:
        if data["actions"] is None:
            raise HTTPException(status_code=400, detail="至少需要允许一个入站动作")
        data["actions"] = inbound_service.validate_actions(data["actions"])
    for key, value in data.items():
        setattr(hook, key, value)
    if hook.process_id is not None and "start_instance" not in (hook.actions or []):
        raise HTTPException(
            status_code=400,
            detail="限定流程的入站 Webhook 必须允许 start_instance",
        )
    secret = inbound_service.generate_secret() if rotate else None
    if secret is not None:
        hook.secret = secret
    audit_service.record(
        db,
        user,
        "UPDATE",
        "inbound_webhook",
        hook.id,
        f"修改入站 Webhook {hook.code}" + ("（已轮换密钥）" if rotate else ""),
    )
    db.commit()
    db.refresh(hook)
    return inbound_service.hook_out(hook, secret)


@router.delete(
    "/inbound-hooks/{hook_id}",
    response_model=DeleteResult,
    summary="删除入站 Webhook 及其事件记录（MANAGER+）",
)
def delete_inbound_hook(hook_id: int, db: DbSession, user: ManagerUser):
    hook = db.get(InboundWebhook, hook_id)
    if hook is None:
        raise HTTPException(status_code=404, detail="入站 Webhook 不存在")
    code = hook.code
    audit_service.record(db, user, "DELETE", "inbound_webhook", hook.id, f"删除入站 Webhook {code}")
    db.delete(hook)
    db.commit()
    return DeleteResult(deleted=1)


@router.get(
    "/inbound-events",
    response_model=List[InboundEventOut],
    summary="入站事件记录（MANAGER+）",
)
def list_inbound_events(
    db: DbSession,
    user: ManagerUser,
    hook_id: Optional[int] = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    stmt = select(InboundEvent)
    if hook_id is not None:
        stmt = stmt.where(InboundEvent.webhook_id == hook_id)
    rows = db.scalars(
        stmt.order_by(InboundEvent.received_at.desc(), InboundEvent.id.desc()).limit(limit)
    ).all()
    return [
        InboundEventOut(
            id=row.id,
            event_id=row.event_id,
            action=row.action,
            status=row.status,
            instance_id=row.instance_id,
            task_id=row.task_id,
            error=row.error,
            received_at=row.received_at,
        )
        for row in rows
    ]
