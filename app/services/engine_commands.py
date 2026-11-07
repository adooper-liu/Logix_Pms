"""Durable cross-database command: persist intent, query original receipt, never replace ID."""

import hashlib
import json
import uuid
from http.client import HTTPException as TransportError

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.engine import EngineCommand
from app.services.engine_transport import RemoteRejected, engine_client

STATUS_LABELS = {
    "PREPARED": "请求已保存",
    "UNKNOWN": "结果待核对",
    "SUCCEEDED": "引擎已确认",
    "REJECTED": "引擎已拒绝",
}
PROVIDER_LABELS = {"LEGACY": "原轻量执行", "FLOWABLE": "Flowable沙箱"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def prepare(db, user, action, target, payload, key, instance_id=None, task_id=None):
    if not user.is_active or user.role == "VIEWER":
        raise HTTPException(403, "无权提交引擎命令")
    if not key or not key.strip() or len(key) > 128:
        raise HTTPException(400, "沙箱命令必须保留有效Idempotency-Key")
    namespace = settings.flowable_sandbox_namespace
    semantic = {"action": action, "target": target, "payload": payload}
    hashed = digest(semantic)
    existing = db.scalar(
        select(EngineCommand).where(
            EngineCommand.namespace == namespace,
            EngineCommand.user_id == user.id,
            EngineCommand.idempotency_key == key,
        )
    )
    if existing:
        if existing.request_hash != hashed:
            raise HTTPException(409, "原命令ID已用于不同请求")
        return existing
    ident = str(uuid.uuid4())
    row = EngineCommand(
        id=ident,
        namespace=namespace,
        user_id=user.id,
        action=action,
        target=target,
        request_hash=hashed,
        request={"command_id": ident, **semantic},
        idempotency_key=key,
        instance_id=instance_id,
        task_id=task_id,
        lock_key=f"{namespace}:instance:{instance_id}" if instance_id else None,
    )
    db.add(row)
    if instance_id:
        from app.models.execution import ProcessInstance

        instance = db.get(ProcessInstance, instance_id)
        instance.sync_status = "PENDING"
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(EngineCommand).where(
                EngineCommand.namespace == namespace,
                EngineCommand.user_id == user.id,
                EngineCommand.idempotency_key == key,
            )
        )
        if existing and existing.request_hash == hashed:
            return existing
        raise HTTPException(409, "该对象有待核对命令，请先恢复原请求") from None
    return row


def dispatch(db, command):
    if command.status in {"SUCCEEDED", "REJECTED"}:
        return command
    posting = False
    try:
        transport = engine_client()
        try:
            receipt = transport.get("/commands/" + command.id)
        except RemoteRejected as error:
            if error.status != 404:
                raise
            posting = True
            receipt = transport.post("/commands", command.request)
        if (
            receipt.get("command_id") != command.id
            or receipt.get("action") != command.action
            or not isinstance(receipt.get("result"), dict)
        ):
            raise ValueError("Invalid command receipt")
        command.receipt = receipt
        command.status = "SUCCEEDED"
        command.error = None
    except RemoteRejected as error:
        command.status = "REJECTED" if posting and 400 <= error.status < 500 else "UNKNOWN"
        command.error = (
            "引擎拒绝请求" if command.status == "REJECTED" else "引擎暂不可用，原请求已保留"
        )
    except (OSError, TransportError, ValueError, HTTPException):
        command.status = "UNKNOWN"
        command.error = "结果待核对，原请求已保留"
    if command.status == "REJECTED":
        command.lock_key = None
    db.commit()
    return command


def out(command):
    return {
        "command_id": command.id,
        "status": command.status,
        "status_label": STATUS_LABELS[command.status],
        "instance_id": command.instance_id,
        "task_id": command.task_id,
        "error": command.error,
    }
