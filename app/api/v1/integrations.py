"""ERP / OA 集成：Webhook 端点管理、Outbox 投递与重试。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import DbSession, ManagerUser
from app.models.integration import IntegrationDelivery, IntegrationEndpoint
from app.schemas.common import DeleteResult
from app.schemas.integration import (
    DeliveryRunResult,
    IntegrationDeliveryOut,
    IntegrationEndpointCreate,
    IntegrationEndpointOut,
    IntegrationEndpointUpdate,
)
from app.services import audit as audit_service
from app.services import integrations as integration_service

router = APIRouter(prefix="/integrations", tags=["集成"])


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
