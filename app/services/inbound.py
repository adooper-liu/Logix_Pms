"""入站 Webhook：ERP/OA 反向启动实例、完成任务。

安全模型：
- 每个 hook 一个密钥，请求体用 HMAC-SHA256 签名，时间戳限制在 ±5 分钟；
- 所有操作以配置的服务账号执行，且该账号必须是 MANAGER / ADMIN；
- `process_id` 非空时只能操作该流程；
- `event_id` 在 hook 内唯一，重复请求返回第一次的结果。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import List, Optional

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.enums import Role
from app.models.integration import InboundEvent, InboundWebhook
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.execution import InstanceStartRequest, TaskCompleteRequest, WorklogCreate
from app.schemas.integration import (
    InboundRequest,
    InboundResult,
    InboundWebhookCreatedOut,
    InboundWebhookOut,
)
from app.services import audit as audit_service
from app.services import execution as execution_service
from app.services import execution_flow as flow_service

ACTIONS = {
    "start_instance": "启动流程",
    "complete_task": "完成任务",
    "record_worklog": "回传实际工时",
    "record_kpi": "回传指标数据点",
}
MANAGER_ROLES = {Role.ADMIN.value, Role.MANAGER.value}
MAX_SKEW_SECONDS = 300
SECRET_BYTES = 32


def generate_secret() -> str:
    return secrets.token_urlsafe(SECRET_BYTES)


def validate_actions(actions: List[str]) -> List[str]:
    unknown = sorted(set(actions) - set(ACTIONS))
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的入站动作：{'、'.join(unknown)}；可选：{'、'.join(ACTIONS)}",
        )
    if not actions:
        raise HTTPException(status_code=400, detail="至少需要允许一个入站动作")
    return [action for action in ACTIONS if action in set(actions)]


def validate_run_as(db: Session, user_id: Optional[int]) -> User:
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="入站服务账号不存在或已停用")
    if user.role not in MANAGER_ROLES:
        raise HTTPException(status_code=400, detail="入站服务账号必须是流程管理科或系统管理员")
    return user


def hook_out(hook: InboundWebhook, secret: Optional[str] = None) -> InboundWebhookOut:
    data = {
        "id": hook.id,
        "code": hook.code,
        "name": hook.name,
        "process_id": hook.process_id,
        "process_code": hook.process.code if hook.process else None,
        "process_name": hook.process.name if hook.process else None,
        "run_as_user_id": hook.run_as_user_id,
        "run_as_user_name": (hook.run_as_user.display_name if hook.run_as_user else None),
        "actions": hook.actions or [],
        "action_labels": [ACTIONS[action] for action in (hook.actions or []) if action in ACTIONS],
        "is_active": hook.is_active,
        "inbound_path": f"/api/v1/integrations/inbound/{hook.code}",
        "last_received_at": hook.last_received_at,
        "created_at": hook.created_at,
        "updated_at": hook.updated_at,
    }
    if secret is None:
        return InboundWebhookOut(**data)
    return InboundWebhookCreatedOut(**data, secret=secret)


def verify_signature(
    secret: str,
    timestamp: Optional[str],
    signature: Optional[str],
    raw_body: bytes,
) -> None:
    if not timestamp or not signature:
        raise HTTPException(
            status_code=401,
            detail="缺少 X-Logix-Timestamp / X-Logix-Signature 请求头",
        )
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="X-Logix-Timestamp 必须是 Unix 秒") from exc
    if abs(time.time() - sent_at) > MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="请求时间戳超出允许窗口（±5 分钟）")

    expected = hmac.new(
        secret.encode("utf-8"),
        timestamp.encode("utf-8") + b"." + raw_body,
        hashlib.sha256,
    ).hexdigest()
    received = signature.strip()
    if received.lower().startswith("sha256="):
        received = received[7:]
    if not hmac.compare_digest(expected, received):
        raise HTTPException(status_code=401, detail="签名校验失败")


def _duplicate_result(event: InboundEvent) -> InboundResult:
    result = InboundResult.model_validate(event.response or {})
    result.duplicate = True
    return result


def _dispatch(
    db: Session,
    hook: InboundWebhook,
    run_as: User,
    payload: InboundRequest,
) -> InboundResult:
    if payload.action == "start_instance":
        if hook.process_id and payload.process_id not in (None, hook.process_id):
            raise HTTPException(status_code=403, detail="该入站 Webhook 只能启动指定流程")
        process_id = hook.process_id or payload.process_id
        if process_id is None:
            raise HTTPException(status_code=400, detail="启动实例需要 process_id")
        process = db.get(ProcessArch, process_id)
        if process is None:
            raise HTTPException(status_code=404, detail="流程不存在")
        request = InstanceStartRequest(
            process_id=process_id,
            project_id=payload.project_id,
            variables=payload.variables,
            assignments=payload.assignments,
        )
        instance = flow_service.start_instance(db, process, run_as, request)
        audit_service.record(
            db,
            run_as,
            "CREATE",
            "process_instance",
            instance.id,
            f"入站 Webhook {hook.code} 启动流程 {instance.code}",
        )
        return InboundResult(
            action=payload.action,
            instance_id=instance.id,
            instance_code=instance.code,
        )

    if payload.action == "complete_task":
        if payload.task_id is None:
            raise HTTPException(status_code=400, detail="完成任务需要 task_id")
        task = execution_service.get_task(db, payload.task_id)
        if hook.process_id and task.instance.process_id != hook.process_id:
            raise HTTPException(status_code=403, detail="该入站 Webhook 只能操作指定流程")
        request = TaskCompleteRequest(
            form_data=payload.form_data,
            variables=payload.variables,
            next_node_key=payload.next_node_key,
            comment=payload.comment,
        )
        flow_service.complete_task(db, task, run_as, request)
        audit_service.record(
            db,
            run_as,
            "UPDATE",
            "process_task",
            task.id,
            f"入站 Webhook {hook.code} 完成任务 {task.name}",
        )
        return InboundResult(
            action=payload.action,
            instance_id=task.instance_id,
            instance_code=task.instance.code,
            task_id=task.id,
            task_status=task.status,
        )

    if payload.action == "record_worklog":
        if payload.task_id is None:
            raise HTTPException(status_code=400, detail="回传工时需要 task_id")
        task = execution_service.get_task(db, payload.task_id)
        if hook.process_id and task.instance.process_id != hook.process_id:
            raise HTTPException(status_code=403, detail="该入站 Webhook 只能操作指定流程")
        worklog = execution_service.record_worklog(
            db,
            task,
            run_as,
            WorklogCreate(
                work_type=payload.work_type or "HANDLE",
                effort_minutes=payload.effort_minutes,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                note=payload.comment,
            ),
        )
        audit_service.record(
            db,
            run_as,
            "CREATE",
            "task_worklog",
            worklog.id,
            f"入站 Webhook {hook.code} 回传任务 {task.name} 工时 {worklog.effort_minutes} 分钟",
        )
        return InboundResult(
            action=payload.action,
            instance_id=task.instance_id,
            instance_code=task.instance.code,
            task_id=task.id,
            task_status=task.status,
            message=f"登记工时 {worklog.effort_minutes} 分钟",
        )

    if payload.action == "record_kpi":
        if payload.kpi_id is None or payload.period is None or payload.value is None:
            raise HTTPException(status_code=400, detail="回传指标需要 kpi_id、period 与 value")
        kpi = db.get(KpiDefinition, payload.kpi_id)
        if kpi is None:
            raise HTTPException(status_code=404, detail="KPI 不存在")
        existing = db.scalar(
            select(KpiRecord).where(
                KpiRecord.kpi_id == payload.kpi_id,
                KpiRecord.period == payload.period,
                KpiRecord.project_id == payload.project_id,
            )
        )
        if existing is not None:
            existing.value = payload.value
            existing.note = payload.comment
            row = existing
        else:
            row = KpiRecord(
                kpi_id=payload.kpi_id,
                period=payload.period,
                value=payload.value,
                project_id=payload.project_id,
                note=payload.comment,
            )
            db.add(row)
        db.flush()
        audit_service.record(
            db,
            run_as,
            "UPDATE" if existing is not None else "CREATE",
            "kpi_record",
            row.id,
            f"入站 Webhook {hook.code} 回传 {kpi.code} {payload.period} 数据点 {payload.value}",
        )
        return InboundResult(
            action=payload.action,
            message=f"{kpi.code} {payload.period} = {payload.value}",
        )

    raise HTTPException(status_code=400, detail=f"不支持的入站动作：{payload.action}")


def receive(
    db: Session,
    code: str,
    raw_body: bytes,
    timestamp: Optional[str],
    signature: Optional[str],
) -> InboundResult:
    hook = db.scalar(select(InboundWebhook).where(InboundWebhook.code == code))
    if hook is None:
        raise HTTPException(status_code=404, detail="入站 Webhook 不存在")
    if not hook.is_active:
        raise HTTPException(status_code=403, detail="入站 Webhook 已停用")
    if not hook.secret:
        raise HTTPException(status_code=403, detail="入站 Webhook 未配置密钥")

    verify_signature(hook.secret, timestamp, signature, raw_body)

    try:
        data = json.loads(raw_body or b"{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="请求体不是合法 JSON") from exc
    try:
        payload = InboundRequest.model_validate(data)
    except ValidationError as exc:
        first = exc.errors()[0]
        raise HTTPException(
            status_code=400,
            detail=f"请求参数错误：{first.get('loc', ('body',))[-1]} {first.get('msg', '')}",
        ) from exc

    allowed = hook.actions or []
    if payload.action not in ACTIONS:
        raise HTTPException(status_code=400, detail=f"未知入站动作：{payload.action}")
    if payload.action not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"该入站 Webhook 不允许动作 {payload.action}",
        )
    if hook.run_as_user_id is None:
        raise HTTPException(status_code=400, detail="入站 Webhook 未配置服务账号")
    run_as = validate_run_as(db, hook.run_as_user_id)

    existing = db.scalar(
        select(InboundEvent).where(
            InboundEvent.webhook_id == hook.id,
            InboundEvent.event_id == payload.event_id,
        )
    )
    if existing is not None:
        return _duplicate_result(existing)

    try:
        result = _dispatch(db, hook, run_as, payload)
        event = InboundEvent(
            webhook_id=hook.id,
            event_id=payload.event_id,
            action=payload.action,
            status="SUCCESS",
            instance_id=result.instance_id,
            task_id=result.task_id,
            response=result.model_dump(mode="json"),
        )
        db.add(event)
        hook.last_received_at = utcnow()
        db.commit()
        return result
    except IntegrityError:
        # 并发重复请求：先提交的一方胜出，另一方回滚后返回同一结果
        db.rollback()
        existing = db.scalar(
            select(InboundEvent).where(
                InboundEvent.webhook_id == hook.id,
                InboundEvent.event_id == payload.event_id,
            )
        )
        if existing is None:
            raise HTTPException(status_code=409, detail="入站事件并发冲突，请重试") from None
        return _duplicate_result(existing)
    except Exception:
        db.rollback()
        raise
