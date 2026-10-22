"""写命令幂等。

用法：
    record = begin(db, "instance.start", key, request_hash(payload))
    if record is not None and record.status == "SUCCESS":
        return replay(record)
    ... 执行命令 ...
    finish(record, response)
    db.commit()
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.execution import IdempotencyRecord

MAX_KEY_LENGTH = 128


def request_hash(payload: BaseModel) -> str:
    raw = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def begin(db: Session, scope: str, key: Optional[str], digest: str) -> Optional[IdempotencyRecord]:
    """返回可回放的记录或新建的 PENDING 占位；无 key 时返回 None。"""
    if key is None:
        return None
    key = key.strip()
    if not key:
        return None
    if len(key) > MAX_KEY_LENGTH:
        raise HTTPException(status_code=400, detail="Idempotency-Key 过长")

    existing = db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != digest:
            raise HTTPException(
                status_code=409,
                detail="Idempotency-Key 已用于不同的请求参数",
            )
        if existing.status == "SUCCESS":
            return existing
        raise HTTPException(status_code=409, detail="相同幂等键的请求正在处理中")

    record = IdempotencyRecord(
        scope=scope,
        key=key,
        request_hash=digest,
        status="PENDING",
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.scope == scope,
                IdempotencyRecord.key == key,
            )
        )
        if (
            existing is not None
            and existing.request_hash == digest
            and existing.status == "SUCCESS"
        ):
            return existing
        raise HTTPException(
            status_code=409, detail="相同幂等键的请求正在处理中，请稍后重试"
        ) from None
    return record


def finish(record: Optional[IdempotencyRecord], response: dict) -> None:
    if record is None:
        return
    record.status = "SUCCESS"
    record.response = response
    record.updated_at = utcnow()
