"""ERP / OA 集成的 Outbox 投递。

- 业务事件只写 delivery（PENDING），不阻塞主请求；
- `/deliveries/run` 批量投递，失败最多重试 3 次（1/2 分钟退避）；
- 每个请求带 `X-Logix-Event` / `X-Logix-Delivery`；配置了 secret 时带
  `X-Logix-Signature: sha256=<HMAC>`，接收方可校验完整性与来源。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import timedelta
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.integration import IntegrationDelivery, IntegrationEndpoint
from app.schemas.integration import (
    DeliveryRunResult,
    IntegrationDeliveryOut,
    IntegrationEndpointOut,
)

MAX_ATTEMPTS = 3
DELIVERY_TIMEOUT = 5
STATUS_LABELS = {"PENDING": "待发送", "SUCCESS": "已送达", "FAILED": "失败"}

EVENT_LABELS = {
    "instance.started": "流程启动",
    "task.created": "任务创建",
    "task.assigned": "任务改派",
    "task.claimed": "任务认领",
    "task.completed": "任务完成",
    "instance.completed": "流程完成",
    "instance.cancelled": "流程取消",
    "exception.created": "异常登记",
    "exception.updated": "异常更新",
}


def validate_events(events) -> list:
    values = list(events or [])
    unknown = [e for e in values if e not in EVENT_LABELS and e != "*"]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail="未知事件类型：" + "、".join(unknown) + "（可用 * 订阅全部）",
        )
    return values


def validate_url(url: str) -> str:
    parsed = urlsplit(url or "")
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Webhook URL 必须是 http(s) 地址")
    return url


def endpoint_out(endpoint: IntegrationEndpoint) -> IntegrationEndpointOut:
    return IntegrationEndpointOut(
        id=endpoint.id,
        code=endpoint.code,
        name=endpoint.name,
        kind=endpoint.kind,
        url=endpoint.url,
        has_secret=bool(endpoint.secret),
        events=endpoint.events or [],
        is_active=endpoint.is_active,
        updated_at=endpoint.updated_at,
    )


def delivery_out(delivery: IntegrationDelivery) -> IntegrationDeliveryOut:
    return IntegrationDeliveryOut(
        id=delivery.id,
        endpoint_id=delivery.endpoint_id,
        endpoint_code=delivery.endpoint.code,
        endpoint_name=delivery.endpoint.name,
        event_type=delivery.event_type,
        payload=delivery.payload or {},
        status=delivery.status,
        status_label=STATUS_LABELS.get(delivery.status, delivery.status),
        attempts=delivery.attempts,
        response_code=delivery.response_code,
        error=delivery.error,
        next_attempt_at=delivery.next_attempt_at,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


def enqueue(db: Session, event_type: str, payload: Dict) -> int:
    """为订阅该事件的活动端点创建 PENDING delivery，返回创建条数。"""
    endpoints = db.scalars(
        select(IntegrationEndpoint).where(IntegrationEndpoint.is_active.is_(True))
    ).all()
    safe = json.loads(json.dumps(payload or {}, ensure_ascii=False, default=str))
    created = 0
    for endpoint in endpoints:
        events = endpoint.events or []
        if events and "*" not in events and event_type not in events:
            continue
        db.add(
            IntegrationDelivery(
                endpoint_id=endpoint.id,
                event_type=event_type,
                payload=safe,
                status="PENDING",
            )
        )
        created += 1
    if created:
        db.flush()
    return created


def _signature(secret: str, body: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return "sha256=" + digest


def _post_json(
    url: str, body: str, headers: Dict[str, str], timeout: int = DELIVERY_TIMEOUT
) -> Tuple[Optional[int], Optional[str]]:
    """返回 (status_code, error)。网络错误时 status_code 为 None。"""
    request = urllib.request.Request(
        url,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, None
    except urllib.error.HTTPError as exc:
        return exc.code, f"HTTP {exc.code}: {exc.reason}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, str(exc)


def deliver_pending(db: Session, limit: int = 50) -> DeliveryRunResult:
    now = utcnow()
    rows = db.scalars(
        select(IntegrationDelivery)
        .where(
            IntegrationDelivery.status == "PENDING",
            or_(
                IntegrationDelivery.next_attempt_at.is_(None),
                IntegrationDelivery.next_attempt_at <= now,
            ),
        )
        .order_by(IntegrationDelivery.created_at, IntegrationDelivery.id)
        .limit(limit)
    ).all()

    processed = delivered = failed = 0
    for delivery in rows:
        endpoint = delivery.endpoint
        processed += 1
        body = json.dumps(
            {
                "event": delivery.event_type,
                "payload": delivery.payload or {},
                "delivery_id": delivery.id,
                "timestamp": now.isoformat() + "Z",
            },
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Logix-PMS/1.0",
            "X-Logix-Event": delivery.event_type,
            "X-Logix-Delivery": str(delivery.id),
        }
        if endpoint.secret:
            headers["X-Logix-Signature"] = _signature(endpoint.secret, body)
        code, error = _post_json(endpoint.url, body, headers)
        delivery.attempts += 1
        delivery.response_code = code
        if code is not None and 200 <= code < 300:
            delivery.status = "SUCCESS"
            delivery.error = None
            delivery.delivered_at = utcnow()
            delivery.next_attempt_at = None
            delivered += 1
        else:
            delivery.error = error or "未收到有效 HTTP 响应"
            if delivery.attempts < MAX_ATTEMPTS:
                delivery.status = "PENDING"
                delivery.next_attempt_at = utcnow() + timedelta(minutes=delivery.attempts)
            else:
                delivery.status = "FAILED"
                delivery.next_attempt_at = None
                failed += 1
    db.flush()

    pending = (
        db.scalar(
            select(func.count())
            .select_from(IntegrationDelivery)
            .where(IntegrationDelivery.status == "PENDING")
        )
        or 0
    )
    return DeliveryRunResult(
        processed=processed, delivered=delivered, failed=failed, pending=pending
    )


def retry_delivery(db: Session, delivery: IntegrationDelivery) -> IntegrationDelivery:
    if delivery.status == "SUCCESS":
        raise HTTPException(status_code=409, detail="已送达的投递不需要重试")
    delivery.status = "PENDING"
    delivery.attempts = 0
    delivery.next_attempt_at = None
    delivery.error = None
    db.flush()
    return delivery
