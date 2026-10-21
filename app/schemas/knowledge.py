"""知识库出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import KnowledgeType, Methodology
from app.schemas.common import ORMModel


class KnowledgeCreate(BaseModel):
    title: str = Field(max_length=200)
    type: KnowledgeType
    methodology: Optional[Methodology] = None
    tags: List[str] = []
    summary: str = Field(max_length=400)
    content: str
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    tool_code: Optional[str] = None
    author: Optional[str] = None


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[KnowledgeType] = None
    methodology: Optional[Methodology] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    tool_code: Optional[str] = None
    author: Optional[str] = None


class KnowledgeReadRequest(BaseModel):
    """记录一次下载/查阅，用于热度排序。"""

    increment: int = Field(default=1, ge=1, le=100)


class KnowledgeOut(ORMModel):
    id: int
    title: str
    type: str
    methodology: Optional[str] = None
    tags: List[str] = []
    summary: str
    content: str
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    tool_code: Optional[str] = None
    author: Optional[str] = None
    download_count: int = 0
    created_at: Optional[UtcDateTime] = None


class KnowledgeBrief(ORMModel):
    id: int
    title: str
    type: str
    methodology: Optional[str] = None
    tags: List[str] = []
    summary: str
    download_count: int = 0
    created_at: Optional[UtcDateTime] = None
