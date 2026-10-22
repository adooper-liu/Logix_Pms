"""超期任务自动升级。

规则来源（按优先级）：
1. 节点分派里的 `escalation_hours` / `escalation_user_id`；
2. 流程执行配置里的默认值；
3. 都没有则不升级。

升级只在实例启动快照里读取，运行中改配置不会影响已启动实例。
扫描由外部 cron 或管理入口触发，不依赖进程内定时器。
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import utcnow
from app.models.enums import InstanceStatus, Role, TaskStatus
from app.models.execution import ProcessInstance, ProcessTask
from app.models.user import User
from app.schemas.execution import EscalationScanResult
from app.services import audit as audit_service
from app.services import execution as execution_service
from app.services import execution_flow as flow_service
from app.services import integrations as integration_service
from app.services import notifications as notification_service

OPEN_STATUSES = (TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)


def _policy(instance: ProcessInstance, node_key: str) -> Tuple[Optional[int], Optional[int]]:
    snapshot = instance.snapshot or {}
    assignment = (snapshot.get("assignments") or {}).get(node_key, {})
    config = snapshot.get("config") or {}
    hours = assignment.get("escalation_hours")
    if hours is None:
        hours = config.get("escalation_hours")
    target_id = assignment.get("escalation_user_id")
    if target_id is None:
        target_id = config.get("escalation_user_id")
    return hours, target_id


def scan_escalations(
    db: Session,
    actor: User,
    process_id: Optional[int] = None,
    limit: int = 500,
) -> EscalationScanResult:
    """扫描已到达升级时限的任务并改派；调用方负责 commit。"""
    now = utcnow()
    stmt = (
        select(ProcessTask)
        .options(joinedload(ProcessTask.instance))
        .where(
            ProcessTask.status.in_(OPEN_STATUSES),
            ProcessTask.due_at.is_not(None),
            ProcessTask.escalated_at.is_(None),
            ProcessTask.instance.has(ProcessInstance.status == InstanceStatus.RUNNING.value),
        )
    )
    if process_id is not None:
        stmt = stmt.join(ProcessInstance, ProcessTask.instance_id == ProcessInstance.id).where(
            ProcessInstance.process_id == process_id
        )
    tasks = db.scalars(stmt.order_by(ProcessTask.due_at, ProcessTask.id).limit(limit)).all()

    result = EscalationScanResult(scanned=len(tasks))
    for task in tasks:
        hours, target_id = _policy(task.instance, task.node_key)
        if hours is None or target_id is None:
            result.skipped += 1
            continue
        if task.due_at is None or task.due_at + timedelta(hours=hours) > now:
            result.skipped += 1
            continue

        target = db.get(User, target_id)
        if target is None or not target.is_active or target.role == Role.VIEWER.value:
            notification_service.notify_managers(
                db,
                "TASK_ESCALATED",
                f"升级失败：{task.name}",
                f"{task.instance.process_name}（{task.instance.code}）· "
                "升级处理人不存在、已停用或为只读账号，请调整升级策略",
                link="execution",
                entity_type="process_task",
                entity_id=task.id,
            )
            result.skipped += 1
            continue
        if task.assignee_user_id == target.id:
            result.skipped += 1
            continue

        previous_id = task.assignee_user_id
        previous_name = task.assignee_name
        previous_status = task.status
        instance = task.instance
        result_update = db.execute(
            update(ProcessTask)
            .where(
                ProcessTask.id == task.id,
                ProcessTask.status.in_(OPEN_STATUSES),
                ProcessTask.escalated_at.is_(None),
                ProcessTask.row_version == task.row_version,
            )
            .values(
                assignee_user_id=target.id,
                assignee_name=target.display_name,
                status=TaskStatus.CLAIMED.value,
                claimed_at=task.claimed_at or now,
                escalated_at=now,
                escalated_to_user_id=target.id,
                escalated_to_name=target.display_name,
                row_version=ProcessTask.row_version + 1,
            )
            .execution_options(synchronize_session=False)
        )
        if result_update.rowcount != 1:
            result.skipped += 1
            continue
        db.flush()
        db.refresh(task)
        execution_service.record_task_event(
            db,
            task,
            "ESCALATED",
            previous_status,
            TaskStatus.CLAIMED.value,
            actor,
            {
                "previous_assignee": previous_name,
                "assignee_user_id": target.id,
                "assignee_name": target.display_name,
            },
        )

        notification_service.notify(
            db,
            target.id,
            "TASK_ESCALATED",
            f"任务已升级给你：{task.name}",
            f"{instance.process_name}（{instance.code}）· 到期 "
            f"{task.due_at:%Y-%m-%d %H:%M}"
            + (f" · 原处理人 {previous_name}" if previous_name else ""),
            link="execution",
            entity_type="process_task",
            entity_id=task.id,
        )
        if previous_id is not None and previous_id != target.id:
            notification_service.notify(
                db,
                previous_id,
                "TASK_ESCALATED",
                f"任务已升级：{task.name}",
                f"{instance.process_name}（{instance.code}）· 已改派给 {target.display_name}",
                link="execution",
                entity_type="process_task",
                entity_id=task.id,
            )

        integration_service.enqueue(db, "task.escalated", flow_service.task_event(task))
        audit_service.record(
            db,
            actor,
            "UPDATE",
            "process_task",
            task.id,
            f"任务升级：{task.name}（{instance.code}）→ {target.display_name}",
        )
        result.escalated += 1
        result.task_ids.append(task.id)

    db.flush()
    return result
