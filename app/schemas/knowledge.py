"""知识库出入参。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Optional

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

    claim: Optional[str] = None
    applicable_when: Optional[str] = None
    not_applicable_when: Optional[str] = None
    input_conditions: Optional[str] = None
    steps_summary: Optional[str] = None
    outputs: Optional[str] = None
    evidence_summary: Optional[str] = None

    scenario_codes: List[str] = []
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)
    step_no: Optional[str] = Field(default=None, max_length=8)
    is_primary: bool = False

    process_id: Optional[int] = None
    project_id: Optional[int] = None
    tool_code: Optional[str] = None
    author: Optional[str] = None
    owner_user_id: Optional[int] = None


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    type: Optional[KnowledgeType] = None
    methodology: Optional[Methodology] = None
    tags: Optional[List[str]] = None
    summary: Optional[str] = None
    content: Optional[str] = None

    claim: Optional[str] = None
    applicable_when: Optional[str] = None
    not_applicable_when: Optional[str] = None
    input_conditions: Optional[str] = None
    steps_summary: Optional[str] = None
    outputs: Optional[str] = None
    evidence_summary: Optional[str] = None

    scenario_codes: Optional[List[str]] = None
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)
    step_no: Optional[str] = Field(default=None, max_length=8)
    is_primary: Optional[bool] = None

    tool_code: Optional[str] = None
    author: Optional[str] = None
    owner_user_id: Optional[int] = None


class KnowledgeReadRequest(BaseModel):
    """记录一次下载/查阅，用于阅读量统计（不参与推荐排序）。"""

    increment: int = Field(default=1, ge=1, le=100)


class KnowledgeOut(ORMModel):
    id: int
    title: str
    type: str
    type_label: Optional[str] = None
    status: str = "PUBLISHED"
    status_label: Optional[str] = None
    methodology: Optional[str] = None
    tags: List[str] = []
    scenario_codes: List[str] = []
    scenario_names: List[str] = []
    stage_nos: List[int] = []
    step_nos: List[str] = []
    primary_step_nos: List[str] = []

    summary: str
    content: str
    claim: Optional[str] = None
    applicable_when: Optional[str] = None
    not_applicable_when: Optional[str] = None
    input_conditions: Optional[str] = None
    steps_summary: Optional[str] = None
    outputs: Optional[str] = None
    evidence_summary: Optional[str] = None

    process_id: Optional[int] = None
    project_id: Optional[int] = None
    tool_code: Optional[str] = None
    author: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    verified_by: Optional[str] = None
    version: int = 1
    is_best_practice: bool = False
    last_verified_at: Optional[UtcDateTime] = None
    review_due_at: Optional[date] = None
    review_overdue: bool = False

    used_count: int = 0
    effective_count: int = 0
    effectiveness_rate: Optional[float] = None

    download_count: int = 0
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class KnowledgeBrief(ORMModel):
    id: int
    title: str
    type: str
    type_label: Optional[str] = None
    status: str = "PUBLISHED"
    status_label: Optional[str] = None
    methodology: Optional[str] = None
    tags: List[str] = []
    scenario_codes: List[str] = []
    scenario_names: List[str] = []
    stage_nos: List[int] = []
    summary: str
    claim: Optional[str] = None
    applicable_when: Optional[str] = None
    not_applicable_when: Optional[str] = None
    owner: Optional[str] = None
    version: int = 1
    is_best_practice: bool = False
    last_verified_at: Optional[UtcDateTime] = None
    review_due_at: Optional[date] = None
    review_overdue: bool = False
    used_count: int = 0
    effective_count: int = 0
    effectiveness_rate: Optional[float] = None
    download_count: int = 0
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class KnowledgeArchiveCandidateOut(KnowledgeBrief):
    """归档候选：超过复核/使用期限仍无人使用的条目，由 Manager 确认后归档。"""

    last_used_at: Optional[UtcDateTime] = None
    unused_days: int = 0


class KnowledgeTypeEffectOut(BaseModel):
    type: str
    type_label: str
    used_count: int = 0
    effective_count: int = 0
    effectiveness_rate: Optional[float] = None


class KnowledgeEffectItemOut(BaseModel):
    id: int
    title: str
    type: str
    type_label: str
    used_count: int = 0
    effective_count: int = 0
    effectiveness_rate: Optional[float] = None


class KnowledgeEffectStatsOut(BaseModel):
    usage_total: int = 0
    effective_count: int = 0
    partial_count: int = 0
    ineffective_count: int = 0
    effectiveness_rate: Optional[float] = None
    by_type: List[KnowledgeTypeEffectOut] = []
    top_items: List[KnowledgeEffectItemOut] = []


class KnowledgeScenarioOut(BaseModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True


class KnowledgeScenarioCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]{2,32}$", description="大写字母/数字/下划线")
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=200)
    sort_order: int = 0
    is_active: bool = True


class KnowledgeScenarioUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=200)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class KnowledgeReviewOut(ORMModel):
    id: int
    knowledge_id: int
    reviewer_user_id: Optional[int] = None
    reviewer: Optional[str] = None
    decision: str
    decision_label: Optional[str] = None
    from_status: Optional[str] = None
    from_status_label: Optional[str] = None
    to_status: Optional[str] = None
    to_status_label: Optional[str] = None
    note: Optional[str] = None
    created_at: Optional[UtcDateTime] = None


class KnowledgeRecommendLogOut(ORMModel):
    id: int
    user_id: Optional[int] = None
    user: Optional[str] = None
    problem: Optional[str] = None
    scenario_codes: List[str] = []
    stage_no: Optional[int] = None
    step_no: Optional[str] = None
    result_ids: List[int] = []
    result_refs: List[Any] = []
    created_at: Optional[UtcDateTime] = None


class KnowledgeStandardMigrationRequest(BaseModel):
    process_id: int
    title: Optional[str] = Field(default=None, max_length=200)
    category: str = Field(default="POLICY", max_length=16)
    description: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    org_unit_id: Optional[int] = None
    node_key: Optional[str] = Field(default=None, max_length=64)


class KnowledgeStandardMigrationOut(BaseModel):
    knowledge_id: int
    document_id: int
    document_code: str
    version_id: int
    version_label: str


class KnowledgeRecommendRequest(BaseModel):
    problem: Optional[str] = Field(default=None, max_length=500)
    scenario_codes: List[str] = []
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)
    step_no: Optional[str] = Field(default=None, max_length=8)
    limit: int = Field(default=6, ge=1, le=20)


class KnowledgeRecommendationOut(BaseModel):
    kind: str = "knowledge"
    id: int
    code: Optional[str] = None
    title: str
    type: str
    type_label: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    summary: str
    score: float
    match_level: str = "mid"
    matched_on: List[str] = []
    scenarios: List[KnowledgeScenarioOut] = []
    claim: Optional[str] = None
    applicable_when: Optional[str] = None
    not_applicable_when: Optional[str] = None
    owner: Optional[str] = None
    tool_code: Optional[str] = None
    is_best_practice: bool = False
    last_verified_at: Optional[UtcDateTime] = None
    review_overdue: bool = False
    used_count: int = 0
    effective_count: int = 0
    effectiveness_rate: Optional[float] = None
    links: Dict[str, str] = {}


class KnowledgeRecommendResponse(BaseModel):
    problem: Optional[str] = None
    scenario_codes: List[str] = []
    items: List[KnowledgeRecommendationOut] = []
    hint: Optional[str] = None


class KnowledgeUsageCreate(BaseModel):
    project_id: Optional[int] = None
    step_no: Optional[str] = Field(default=None, max_length=8)
    outcome: str = Field(default="EFFECTIVE", pattern="^(EFFECTIVE|PARTIAL|INEFFECTIVE)$")
    note: Optional[str] = None
    evidence_url: Optional[str] = Field(default=None, max_length=500)


class KnowledgeUsageOut(ORMModel):
    id: int
    knowledge_id: int
    project_id: Optional[int] = None
    step_no: Optional[str] = None
    used_by_user_id: Optional[int] = None
    used_by: Optional[str] = None
    used_at: UtcDateTime
    outcome: str
    outcome_label: Optional[str] = None
    note: Optional[str] = None
    evidence_url: Optional[str] = None


class KnowledgeReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: Optional[str] = Field(default=None, max_length=500)


class KnowledgeMetaOut(BaseModel):
    type_labels: dict
    status_labels: dict
    outcome_labels: dict
    stats: dict
    scenarios: List[KnowledgeScenarioOut] = []


class KnowledgeStatsOut(BaseModel):
    total: int = 0
    verified: int = 0
    published: int = 0
    pending_review: int = 0
    review_overdue: int = 0
    archived: int = 0
    best_practice: int = 0


# 兼容旧引用
KnowledgeStatusOut = KnowledgeStatsOut
