"""取消补偿出入参。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class CompensationActionCreate(BaseModel):
    node_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    is_active: bool = True


class CompensationActionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CompensationActionOut(ORMModel):
    id: int
    process_id: int
    node_key: str
    name: str
    description: Optional[str] = None
    is_active: bool = True
    created_at: UtcDateTime


class CompensationRecordOut(ORMModel):
    id: int
    instance_id: int
    task_id: Optional[int] = None
    node_key: str
    action_name: str
    description: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    note: Optional[str] = None
    completed_at: Optional[UtcDateTime] = None
    completed_by_user_id: Optional[int] = None
    completed_by: Optional[str] = None
    created_at: UtcDateTime


class CompensationCompleteIn(BaseModel):
    note: Optional[str] = None
