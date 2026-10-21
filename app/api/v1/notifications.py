"""站内通知：列表、未读数、已读与逾期扫描。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.notification import Notification
from app.schemas.notification import (
    NotificationOut,
    NotificationScanResult,
    NotificationSummary,
)
from app.services import notifications as notification_service

router = APIRouter(prefix="/notifications", tags=["通知"])


@router.get("", response_model=List[NotificationOut], summary="我的通知列表")
def list_notifications(
    db: DbSession,
    user: CurrentUser,
    unread_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
):
    return notification_service.list_for_user(db, user.id, unread_only=unread_only, limit=limit)


@router.get("/summary", response_model=NotificationSummary, summary="未读数汇总")
def notification_summary(db: DbSession, user: CurrentUser):
    return notification_service.summary(db, user.id)


@router.post("/read-all", summary="全部标记为已读")
def read_all(db: DbSession, user: CurrentUser):
    updated = notification_service.mark_all_read(db, user.id)
    db.commit()
    return {"updated": updated}


@router.post(
    "/scan", response_model=NotificationScanResult, summary="扫描逾期并生成提醒（MANAGER+）"
)
def scan(db: DbSession, user: ManagerUser):
    result = notification_service.scan_overdue(db)
    db.commit()
    return result


@router.post("/{notification_id}/read", response_model=NotificationOut, summary="标记单条已读")
def read_one(notification_id: int, db: DbSession, user: CurrentUser):
    obj = db.get(Notification, notification_id)
    if obj is None or obj.user_id != user.id:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification_service.mark_read(db, obj)
    db.commit()
    db.refresh(obj)
    return notification_service.out(obj)
