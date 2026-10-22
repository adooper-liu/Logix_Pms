"""流程执行编排层。

把「状态推进」和它必然产生的副作用（站内通知、Outbox 事件）放在一起：
- 前端 API 与入站 Webhook 复用同一套编排，避免两条路径产生不同的事件；
- execution.py 仍然只负责实例/任务的纯状态与约束，不依赖通知和集成。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import InstanceStatus, TaskStatus
from app.models.execution import ProcessInstance, ProcessTask
from app.models.process import ProcessArch
from app.models.user import User
from app.schemas.execution import InstanceStartRequest, TaskCompleteRequest
from app.services import execution as execution_service
from app.services import integrations as integration_service
from app.services import notifications as notification_service


def open_task(db: Session, instance_id: int):
    return db.scalar(
        select(ProcessTask)
        .where(
            ProcessTask.instance_id == instance_id,
            ProcessTask.status.in_((TaskStatus.PENDING.value, TaskStatus.CLAIMED.value)),
        )
        .order_by(ProcessTask.id)
    )


def notify_open_task(db: Session, instance: ProcessInstance) -> None:
    task = open_task(db, instance.id)
    if task is None:
        return
    if task.assignee_user_id is not None:
        notification_service.notify(
            db,
            task.assignee_user_id,
            "TASK_ASSIGNED",
            f"新任务：{task.name}",
            f"{instance.process_name}（{instance.code}）",
            link="execution",
            entity_type="process_task",
            entity_id=task.id,
        )
        return
    # 公共队列任务没有明确处理人：提醒流程管理科/管理员，避免任务静默积压
    notification_service.notify_managers(
        db,
        "TASK_ASSIGNED",
        f"公共任务待认领：{task.name}",
        f"{instance.process_name}（{instance.code}）"
        + (f" · 候选：{task.candidate_role}" if task.candidate_role else ""),
        link="execution",
        entity_type="process_task",
        entity_id=task.id,
    )


def instance_event(instance: ProcessInstance) -> dict:
    return {
        "instance_id": instance.id,
        "code": instance.code,
        "process_id": instance.process_id,
        "process_name": instance.process_name,
        "project_id": instance.project_id,
        "status": instance.status,
        "current_node_key": instance.current_node_key,
        "started_by_id": instance.started_by_id,
        "started_by_name": instance.started_by_name,
        "started_at": instance.started_at,
        "suspended_at": instance.suspended_at,
        "suspend_reason": instance.suspend_reason,
    }


def task_event(task: ProcessTask) -> dict:
    return {
        "task_id": task.id,
        "instance_id": task.instance_id,
        "instance_code": task.instance.code,
        "process_name": task.instance.process_name,
        "node_key": task.node_key,
        "name": task.name,
        "task_type": task.task_type,
        "status": task.status,
        "assignee_user_id": task.assignee_user_id,
        "assignee_name": task.assignee_name,
        "created_at": task.created_at,
        "due_at": task.due_at,
        "escalated_at": task.escalated_at,
        "escalated_to_user_id": task.escalated_to_user_id,
        "escalated_to_name": task.escalated_to_name,
    }


def start_instance(
    db: Session,
    process: ProcessArch,
    user: User,
    payload: InstanceStartRequest,
) -> ProcessInstance:
    instance = execution_service.start_instance(db, process, user, payload)
    notify_open_task(db, instance)
    integration_service.enqueue(db, "instance.started", instance_event(instance))
    opened = open_task(db, instance.id)
    if opened is not None:
        integration_service.enqueue(db, "task.created", task_event(opened))
    return instance


def complete_task(
    db: Session,
    task: ProcessTask,
    user: User,
    payload: TaskCompleteRequest,
) -> ProcessTask:
    execution_service.complete_task(db, task, user, payload)
    instance = task.instance
    if instance.status == InstanceStatus.COMPLETED.value:
        if instance.started_by_id:
            notification_service.notify(
                db,
                instance.started_by_id,
                "INSTANCE_COMPLETED",
                f"流程已完成：{instance.process_name}",
                f"{instance.code}",
                link="execution",
                entity_type="process_instance",
                entity_id=instance.id,
            )
    else:
        notify_open_task(db, instance)

    integration_service.enqueue(db, "task.completed", task_event(task))
    if instance.status == InstanceStatus.COMPLETED.value:
        integration_service.enqueue(db, "instance.completed", instance_event(instance))
    else:
        following = open_task(db, instance.id)
        if following is not None:
            integration_service.enqueue(db, "task.created", task_event(following))
    return task
