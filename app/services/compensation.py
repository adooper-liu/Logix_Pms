"""取消补偿动作、补偿待办与实例归档。"""

from __future__ import annotations

from datetime import timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import utcnow
from app.models.compensation import CompensationAction, CompensationRecord
from app.models.execution import ProcessInstance
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.compensation import CompensationActionOut, CompensationRecordOut

STATUS_LABELS = {"PENDING": "待补偿", "DONE": "已完成", "CANCELLED": "已取消"}


class CompensationError(ValueError):
    pass


def action_out(row: CompensationAction) -> CompensationActionOut:
    return CompensationActionOut(
        id=row.id,
        process_id=row.process_id,
        node_key=row.node_key,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        created_at=row.created_at,
    )


def record_out(row: CompensationRecord) -> CompensationRecordOut:
    return CompensationRecordOut(
        id=row.id,
        instance_id=row.instance_id,
        task_id=row.task_id,
        node_key=row.node_key,
        action_name=row.action_name,
        description=row.description,
        status=row.status,
        status_label=STATUS_LABELS.get(row.status, row.status),
        note=row.note,
        completed_at=row.completed_at,
        completed_by_user_id=row.completed_by_user_id,
        completed_by=row.completed_by.display_name if row.completed_by else None,
        created_at=row.created_at,
    )


def list_actions(db: Session, process_id: int) -> List[CompensationAction]:
    return list(
        db.scalars(
            select(CompensationAction)
            .where(CompensationAction.process_id == process_id)
            .order_by(CompensationAction.node_key)
        ).all()
    )


def upsert_action(db: Session, process_id: int, data: dict) -> CompensationAction:
    if db.get(ProcessArch, process_id) is None:
        raise CompensationError("流程不存在")
    row = db.scalar(
        select(CompensationAction).where(
            CompensationAction.process_id == process_id,
            CompensationAction.node_key == data["node_key"],
        )
    )
    if row is None:
        row = CompensationAction(
            process_id=process_id,
            node_key=data["node_key"],
            name=data["name"],
            description=data.get("description"),
            is_active=data.get("is_active", True),
        )
        db.add(row)
    else:
        for field in ("name", "description", "is_active"):
            if field in data:
                setattr(row, field, data[field])
    db.flush()
    return row


def records_for_instance(db: Session, instance_id: int) -> List[CompensationRecord]:
    return list(
        db.scalars(
            select(CompensationRecord)
            .options(joinedload(CompensationRecord.completed_by))
            .where(CompensationRecord.instance_id == instance_id)
            .order_by(CompensationRecord.id)
        ).all()
    )


def create_records_on_cancel(db: Session, instance: ProcessInstance) -> int:
    """取消时按已完成任务倒序生成补偿待办；同一任务只生成一次。"""
    existing = {
        row.task_id
        for row in db.scalars(
            select(CompensationRecord).where(CompensationRecord.instance_id == instance.id)
        ).all()
        if row.task_id is not None
    }
    actions = {
        row.node_key: row
        for row in db.scalars(
            select(CompensationAction).where(
                CompensationAction.process_id == instance.process_id,
                CompensationAction.is_active.is_(True),
            )
        ).all()
    }
    completed = sorted(
        (task for task in instance.tasks if task.status == "COMPLETED" and task.id not in existing),
        key=lambda task: (task.completed_at or task.created_at, task.id),
        reverse=True,
    )
    created = 0
    for task in completed:
        action = actions.get(task.node_key)
        if action is None:
            continue
        db.add(
            CompensationRecord(
                instance_id=instance.id,
                task_id=task.id,
                node_key=task.node_key,
                action_name=action.name,
                description=action.description,
                status="PENDING",
            )
        )
        created += 1
    db.flush()
    return created


def complete_record(
    db: Session, row: CompensationRecord, user: User, note: Optional[str]
) -> CompensationRecord:
    if row.status != "PENDING":
        raise CompensationError("只有待补偿记录可以完成")
    row.status = "DONE"
    row.note = note
    row.completed_at = utcnow()
    row.completed_by_user_id = user.id
    db.flush()
    return row


def archive_instances(db: Session, older_than_days: int) -> int:
    if older_than_days < 1:
        raise CompensationError("归档天数必须大于 0")
    cutoff = utcnow() - timedelta(days=older_than_days)
    rows = db.scalars(
        select(ProcessInstance).where(
            ProcessInstance.status.in_(("COMPLETED", "CANCELLED")),
            ProcessInstance.completed_at.is_not(None),
            ProcessInstance.completed_at < cutoff,
            ProcessInstance.archived_at.is_(None),
        )
    ).all()
    now = utcnow()
    for row in rows:
        row.archived_at = now
    db.flush()
    return len(rows)


def archived_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(ProcessInstance)
            .where(ProcessInstance.archived_at.is_not(None))
        )
        or 0
    )
