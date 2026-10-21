"""通知出入参。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime


class NotificationOut(BaseModel):
    id: int
    type: str
    type_label: str
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    is_read: bool
    created_at: UtcDateTime
    read_at: Optional[UtcDateTime] = None


class NotificationSummary(BaseModel):
    unread: int = 0
    by_type: Dict[str, int] = {}


class NotificationScanResult(BaseModel):
    created: int = 0
    scanned: int = 0


class NotificationList(BaseModel):
    items: List[NotificationOut] = Field(default_factory=list)
