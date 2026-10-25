"""L5 任务目录：L4 活动下的任务定义与工时汇总。"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models.process import ProcessArch
from app.models.process_task import ProcessTaskDefinition
from app.schemas.process_task import (
    ProcessTaskOut,
    ProcessTaskRollupOut,
)

MAX_LEVEL = 4


class ProcessTaskError(ValueError):
    pass


def task_out(row: ProcessTaskDefinition) -> ProcessTaskOut:
    return ProcessTaskOut(
        id=row.id,
        activity_id=row.activity_id,
        activity_code=row.activity.code if row.activity else None,
        activity_name=row.activity.name if row.activity else None,
        code=row.code,
        name=row.name,
        description=row.description,
        position_id=row.position_id,
        position_name=row.position.name if row.position else None,
        standard_minutes=row.standard_minutes,
        frequency=row.frequency,
        is_active=row.is_active,
        sort_order=row.sort_order,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _require_activity(db: Session, activity_id: int) -> ProcessArch:
    activity = db.get(ProcessArch, activity_id)
    if activity is None or activity.level != MAX_LEVEL:
        raise ProcessTaskError("L5 任务必须挂在 L4 活动下")
    return activity


def list_tasks(
    db: Session,
    activity_id: Optional[int] = None,
    process_id: Optional[int] = None,
    include_inactive: bool = False,
    limit: int = 500,
) -> List[ProcessTaskDefinition]:
    stmt = (
        select(ProcessTaskDefinition)
        .options(
            joinedload(ProcessTaskDefinition.activity),
            joinedload(ProcessTaskDefinition.position),
        )
        .order_by(
            ProcessTaskDefinition.activity_id,
            ProcessTaskDefinition.sort_order,
            ProcessTaskDefinition.id,
        )
    )
    if activity_id is not None:
        stmt = stmt.where(ProcessTaskDefinition.activity_id == activity_id)
    if process_id is not None:
        stmt = stmt.join(ProcessArch, ProcessArch.id == ProcessTaskDefinition.activity_id).where(
            ProcessArch.parent_id == process_id
        )
    if not include_inactive:
        stmt = stmt.where(ProcessTaskDefinition.is_active.is_(True))
    return list(db.scalars(stmt.limit(limit)).all())


def create_task(db: Session, data: dict) -> ProcessTaskDefinition:
    _require_activity(db, data["activity_id"])
    if db.scalar(
        select(ProcessTaskDefinition).where(
            ProcessTaskDefinition.activity_id == data["activity_id"],
            ProcessTaskDefinition.code == data["code"],
        )
    ):
        raise ProcessTaskError(f"该活动下任务编码 {data['code']} 已存在")
    row = ProcessTaskDefinition(**data)
    db.add(row)
    db.flush()
    return row


def update_task(db: Session, row: ProcessTaskDefinition, data: dict) -> ProcessTaskDefinition:
    if "code" in data and data["code"] != row.code:
        if db.scalar(
            select(ProcessTaskDefinition).where(
                ProcessTaskDefinition.activity_id == row.activity_id,
                ProcessTaskDefinition.code == data["code"],
                ProcessTaskDefinition.id != row.id,
            )
        ):
            raise ProcessTaskError(f"该活动下任务编码 {data['code']} 已存在")
    for field, value in data.items():
        setattr(row, field, value)
    db.flush()
    return row


def rollup(db: Session, activity_id: int) -> ProcessTaskRollupOut:
    activity = _require_activity(db, activity_id)
    rows = list_tasks(db, activity_id=activity_id)
    total = sum(row.standard_minutes or 0 for row in rows)
    return ProcessTaskRollupOut(
        activity_id=activity.id,
        activity_code=activity.code,
        activity_name=activity.name,
        tasks=[task_out(row) for row in rows],
        task_count=len(rows),
        total_standard_minutes=round(total, 2),
    )


def count_by_activity(db: Session, activity_id: int) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProcessTaskDefinition)
            .where(
                ProcessTaskDefinition.activity_id == activity_id,
                ProcessTaskDefinition.is_active.is_(True),
            )
        )
        or 0
    )
