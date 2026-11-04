"""复制资产包出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.common import ORMModel


class ReplicationPackCreate(BaseModel):
    round_id: Optional[int] = Field(default=None, ge=1)
    receiver_user_id: Optional[int] = Field(default=None, ge=1)
    source_project_id: Optional[int] = None
    title: str = Field(min_length=1, max_length=200)
    conditions: Optional[str] = None
    benefit_evidence: Optional[str] = None
    failure_notes: Optional[str] = None
    knowledge_ids: List[int] = []
    document_ids: List[int] = []
    template_ids: List[int] = []


class ReplicationPackUpdate(BaseModel):
    expected_revision: Optional[int] = Field(default=None, ge=0)
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


class ReplicationReceiptIn(BaseModel):
    expected_revision: int = Field(ge=0)
    target_process_id: int = Field(ge=1)
    decision: str = Field(pattern="^(ACCEPT|REJECT)$")
    evidence: str = Field(min_length=1, max_length=2000)


class ReplicationPackOut(ORMModel):
    source_snapshot: Optional[dict] = None
    receiver_user_id: Optional[int] = None
    receipt: Optional[dict] = None
    revision: int = 0
    receipt_label: str = "接收待确认；不代表本地上线"
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
