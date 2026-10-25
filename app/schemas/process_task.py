"""L5 任务定义出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class ProcessTaskCreate(BaseModel):
    activity_id: int
    code: str = Field(min_length=1, max_length=48)
    name: str = Field(min_length=1, max_length=128)
    description: Optional[str] = None
    position_id: Optional[int] = None
    standard_minutes: Optional[float] = Field(default=None, ge=0)
    frequency: Optional[str] = Field(default=None, max_length=32)
    sort_order: int = 0


class ProcessTaskUpdate(BaseModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=48)
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    description: Optional[str] = None
    position_id: Optional[int] = None
    standard_minutes: Optional[float] = Field(default=None, ge=0)
    frequency: Optional[str] = Field(default=None, max_length=32)
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class ProcessTaskOut(ORMModel):
    id: int
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    code: str
    name: str
    description: Optional[str] = None
    position_id: Optional[int] = None
    position_name: Optional[str] = None
    standard_minutes: Optional[float] = None
    frequency: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class ProcessTaskRollupOut(BaseModel):
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    tasks: List[ProcessTaskOut] = []
    task_count: int = 0
    total_standard_minutes: float = 0.0
