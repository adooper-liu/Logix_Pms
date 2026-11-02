"""待确认的异常：从已有红黄指标和超时任务带出，不直接写入台账。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.timeutil import utcnow
from app.models.enums import ExceptionStatus, InstanceStatus, TaskStatus
from app.models.execution import ProcessTask
from app.models.monitor import ExceptionEvent, KpiDefinition
from app.schemas.monitor import ExceptionSuggestion
from app.services import kpi as kpi_service

_OPEN = (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)


def suggestions(db: Session, limit: int = 8) -> list[ExceptionSuggestion]:
    open_rows = db.scalars(select(ExceptionEvent).where(ExceptionEvent.status.in_(_OPEN))).all()
    taken_kpis = {row.source_kpi_id for row in open_rows if row.source_kpi_id}
    taken_instances = {row.source_instance_id for row in open_rows if row.source_instance_id}
    rows: list[ExceptionSuggestion] = []

    kpis = db.scalars(
        select(KpiDefinition)
        .options(selectinload(KpiDefinition.records))
        .where(KpiDefinition.is_active.is_(True))
    ).all()
    for kpi in kpis:
        if kpi.id in taken_kpis:
            continue
        records = kpi_service.ordered_records(kpi.records)
        latest = records[-1].value if records else None
        status, _label, kind = kpi_service.presentation(db, kpi, latest)
        if kind == kpi_service.INTAKE_DRAFT or status not in ("RED", "YELLOW"):
            continue
        tone = "红" if status == "RED" else "黄"
        rows.append(
            ExceptionSuggestion(
                source="kpi",
                kpi_id=kpi.id,
                process_id=kpi.process_id,
                title=f"{kpi.name} 当前为{tone}",
                description=(f"{kpi.code} 已有正式来源，最新值处于{tone}。确认后才写入异常台账。"),
                severity="HIGH" if status == "RED" else "MEDIUM",
            )
        )
        if len(rows) >= limit:
            return rows

    now = utcnow()
    tasks = db.scalars(
        select(ProcessTask)
        .options(selectinload(ProcessTask.instance))
        .where(
            ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
            ProcessTask.due_at.is_not(None),
            ProcessTask.due_at < now,
        )
    ).all()
    seen_instances: set[int] = set()
    for task in tasks:
        instance = task.instance
        if instance is None or instance.status != InstanceStatus.RUNNING.value:
            continue
        if instance.id in taken_instances or instance.id in seen_instances:
            continue
        seen_instances.add(instance.id)
        rows.append(
            ExceptionSuggestion(
                source="instance",
                instance_id=instance.id,
                process_id=instance.process_id,
                title=f"{instance.code} {task.name} 已超过时限",
                description=(
                    f"实例 {instance.code} 的待办「{task.name}」已过要求时间。"
                    "确认后才写入异常台账。"
                ),
                severity="HIGH",
            )
        )
        if len(rows) >= limit:
            break
    return rows
