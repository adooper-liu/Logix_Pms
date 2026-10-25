"""复制资产包出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class ReplicationPackCreate(BaseModel):
    source_project_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=200)
    conditions: Optional[str] = None
    benefit_evidence: Optional[str] = None
    failure_notes: Optional[str] = None
    knowledge_ids: List[int] = []
    document_ids: List[int] = []
    template_ids: List[int] = []


class ReplicationPackUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    conditions: Optional[str] = None
    benefit_evidence: Optional[str] = None
    failure_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    status: Optional[str] = Field(default=None, pattern="^(DRAFT|PUBLISHED|REJECTED)$")
    knowledge_ids: Optional[List[int]] = None
    document_ids: Optional[List[int]] = None
    template_ids: Optional[List[int]] = None


class ReplicationAssetOut(BaseModel):
    id: int
    code: Optional[str] = None
    title: str


class ReplicationPackOut(ORMModel):
    id: int
    source_project_id: Optional[int] = None
    source_project_code: Optional[str] = None
    title: str
    conditions: Optional[str] = None
    benefit_evidence: Optional[str] = None
    failure_notes: Optional[str] = None
    rejection_reason: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = None
    knowledge: List[ReplicationAssetOut] = []
    documents: List[ReplicationAssetOut] = []
    templates: List[ReplicationAssetOut] = []
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None
