"""文档候选活动契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DocumentCandidateOut(BaseModel):
    id: int
    document_version_id: int
    process_id: int
    line_no: int
    text: str
    name: str
    confidence: str
    status: str
    activity_id: Optional[int] = None
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    created_by_name: Optional[str] = None
    confirmed_by_name: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class DocumentExtractIn(BaseModel):
    document_version_id: int = Field(ge=1)
    force: bool = False


class DocumentCandidateConfirmIn(BaseModel):
    name: Optional[str] = Field(default=None, max_length=128)
    code: Optional[str] = Field(default=None, max_length=32)
    owner: Optional[str] = Field(default=None, max_length=64)
