"""通知的生成、查询、已读与逾期扫描。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ExceptionStatus, StepStatus
from app.models.monitor import ExceptionEvent
from app.models.notification import Notification
from app.models.project import Project, ProjectStep
from app.schemas.notification import (
    NotificationOut,
    NotificationScanResult,
    NotificationSummary,
)

TYPE_LABELS = {
    "TASK_ASSIGNED": "任务指派",
    "TASK_COMPLETED": "任务完成",
    "INSTANCE_COMPLETED": "流程完成",
    "INSTANCE_CANCELLED": "流程取消",
    "EXCEPTION_ASSIGNED": "异常指派",
    "EXCEPTION_OVERDUE": "异常超期",
    "MILESTONE_OVERDUE": "里程碑逾期",
    "SYSTEM": "系统通知",
}


def notify(
    db: Session,
    user_id: Optional[int],
    type_: str,
    title: str,
    body: Optional[str] = None,
    link: Optional[str] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
) -> Optional[Notification]:
    """创建通知；同一用户/类型/实体已有未读时跳过，避免重复提醒。"""
    if user_id is None:
        return None
    if entity_type and entity_id is not None:
        existing = db.scalar(
            select(Notification).where(
                Notification.user_id == user_id,
                Notification.type == type_,
                Notification.entity_type == entity_type,
                Notification.entity_id == entity_id,
                Notification.is_read.is_(False),
            )
        )
        if existing is not None:
            return existing
    notification = Notification(
        user_id=user_id,
        type=type_,
        title=title,
        body=body,
        link=link,
        entity_type=entity_type,
        entity_id=entity_id,
    )
    db.add(notification)
    db.flush()
    return notification


def out(notification: Notification) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        type=notification.type,
        type_label=TYPE_LABELS.get(notification.type, notification.type),
        title=notification.title,
        body=notification.body,
        link=notification.link,
        entity_type=notification.entity_type,
        entity_id=notification.entity_id,
        is_read=notification.is_read,
        created_at=notification.created_at,
        read_at=notification.read_at,
    )


def list_for_user(
    db: Session, user_id: int, unread_only: bool = False, limit: int = 50
) -> List[NotificationOut]:
    stmt = select(Notification).where(Notification.user_id == user_id)
    if unread_only:
        stmt = stmt.where(Notification.is_read.is_(False))
    rows = db.scalars(
        stmt.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit)
    ).all()
    return [out(n) for n in rows]


def summary(db: Session, user_id: int) -> NotificationSummary:
    rows = db.execute(
        select(Notification.type, func.count(Notification.id))
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .group_by(Notification.type)
    ).all()
    by_type: Dict[str, int] = {type_: count for type_, count in rows}
    return NotificationSummary(unread=sum(by_type.values()), by_type=by_type)


def mark_read(db: Session, notification: Notification) -> Notification:
    if not notification.is_read:
        from app.core.timeutil import utcnow

        notification.is_read = True
        notification.read_at = utcnow()
        db.flush()
    return notification


def mark_all_read(db: Session, user_id: int) -> int:
    from app.core.timeutil import utcnow

    rows = db.scalars(
        select(Notification).where(Notification.user_id == user_id, Notification.is_read.is_(False))
    ).all()
    now = utcnow()
    for row in rows:
        row.is_read = True
        row.read_at = now
    db.flush()
    return len(rows)


def scan_overdue(db: Session) -> NotificationScanResult:
    """扫描逾期异常与里程碑，生成去重后的提醒。需要调用方 commit。"""
    scanned = 0
    created_before = db.scalar(select(func.count()).select_from(Notification)) or 0

    exceptions = db.scalars(
        select(ExceptionEvent).where(
            ExceptionEvent.status.in_(
                (ExceptionStatus.OPEN.value, ExceptionStatus.IN_PROGRESS.value)
            ),
            ExceptionEvent.due_at.is_not(None),
            ExceptionEvent.owner_user_id.is_not(None),
        )
    ).all()
    from app.core.timeutil import utcnow

    now = utcnow()
    for event in exceptions:
        scanned += 1
        if event.due_at and event.due_at < now:
            notify(
                db,
                event.owner_user_id,
                "EXCEPTION_OVERDUE",
                f"异常已超期：{event.title}",
                f"{event.code} · 要求闭环时间 {event.due_at:%Y-%m-%d %H:%M}",
                link="monitor",
                entity_type="exception",
                entity_id=event.id,
            )

    milestones = db.execute(
        select(ProjectStep, Project)
        .join(Project, ProjectStep.project_id == Project.id)
        .where(
            ProjectStep.is_milestone.is_(True),
            ProjectStep.status != StepStatus.DONE.value,
            ProjectStep.due_date.is_not(None),
            Project.owner_user_id.is_not(None),
        )
    ).all()
    today = date.today()
    for step, project in milestones:
        scanned += 1
        if step.due_date and step.due_date < today:
            notify(
                db,
                project.owner_user_id,
                "MILESTONE_OVERDUE",
                f"里程碑逾期：{step.name}",
                f"{project.code} {project.name} · 计划日期 {step.due_date}",
                link="projects",
                entity_type="project_step",
                entity_id=step.id,
            )

    created_after = db.scalar(select(func.count()).select_from(Notification)) or 0
    return NotificationScanResult(created=created_after - created_before, scanned=scanned)
