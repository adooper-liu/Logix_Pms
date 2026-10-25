"""BPMN 评论出入参。"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class CommentCreate(BaseModel):
    element_id: str = Field(min_length=1, max_length=64)
    element_name: Optional[str] = Field(default=None, max_length=128)
    element_type: Optional[str] = Field(default=None, max_length=32)
    body: str = Field(min_length=1)


class CommentOut(ORMModel):
    id: int
    process_id: int
    element_id: str
    element_name: Optional[str] = None
    element_type: Optional[str] = None
    body: str
    status: str
    status_label: Optional[str] = None
    author_user_id: Optional[int] = None
    author_name: Optional[str] = None
    resolved_by_user_id: Optional[int] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[UtcDateTime] = None
    created_at: UtcDateTime
