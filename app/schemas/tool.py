"""工具箱出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import ToolCategory, ToolDifficulty
from app.schemas.common import ORMModel
from app.schemas.knowledge import KnowledgeBrief, KnowledgeScenarioOut


class ToolOut(ORMModel):
    id: int
    code: str
    name: str
    alias: Optional[str] = None
    category: str
    category_label: Optional[str] = None
    stage_no: int
    purpose: str
    when_to_use: str
    steps: List[str] = []
    template_ref: Optional[str] = None
    pitfalls: Optional[str] = None

    scenario_codes: List[str] = []
    scenario_names: List[str] = []
    knowledge_count: int = 0
    difficulty: str = "MEDIUM"
    difficulty_label: Optional[str] = None
    typical_duration: Optional[str] = None
    prerequisites: Optional[str] = None
    not_applicable_when: Optional[str] = None
    verification_standard: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    version: int = 1
    status: str = "PUBLISHED"
    status_label: Optional[str] = None
    last_verified_at: Optional[UtcDateTime] = None
    review_due_at: Optional[date] = None
    review_overdue: bool = False
    is_active: bool = True


class ToolBrief(ORMModel):
    id: int
    code: str
    name: str
    category: str
    category_label: Optional[str] = None
    stage_no: int
    purpose: str
    when_to_use: Optional[str] = None

    scenario_codes: List[str] = []
    scenario_names: List[str] = []
    knowledge_count: int = 0
    difficulty: str = "MEDIUM"
    difficulty_label: Optional[str] = None
    typical_duration: Optional[str] = None
    verification_standard: Optional[str] = None
    owner: Optional[str] = None
    review_due_at: Optional[date] = None
    review_overdue: bool = False
    status: str = "PUBLISHED"
    status_label: Optional[str] = None
    is_active: bool = True


class ToolWorkflowStepOut(BaseModel):
    step_no: str
    name: str
    stage_no: int


class ToolUsageSummary(BaseModel):
    used: int = 0
    effective: int = 0
    rate: Optional[float] = None


class ToolUsageCreate(BaseModel):
    project_id: Optional[int] = None
    step_no: Optional[str] = Field(default=None, max_length=8)
    outcome: str = Field(default="EFFECTIVE", pattern="^(EFFECTIVE|PARTIAL|INEFFECTIVE)$")
    note: Optional[str] = None
    evidence_url: Optional[str] = Field(default=None, max_length=500)


class ToolUsageOut(ORMModel):
    id: int
    tool_code: str
    project_id: Optional[int] = None
    step_no: Optional[str] = None
    used_by_user_id: Optional[int] = None
    used_by: Optional[str] = None
    used_at: UtcDateTime
    outcome: str
    outcome_label: Optional[str] = None
    note: Optional[str] = None
    evidence_url: Optional[str] = None


class ToolDetailOut(ToolOut):
    usage: ToolUsageSummary = ToolUsageSummary()
    knowledge: List[KnowledgeBrief] = []
    workflow_steps: List[ToolWorkflowStepOut] = []
    usage_events: List[ToolUsageOut] = []


class ToolCreate(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_-]{2,32}$")
    name: str = Field(min_length=1, max_length=64)
    alias: Optional[str] = Field(default=None, max_length=96)
    category: ToolCategory
    stage_no: int = Field(ge=1, le=5)
    purpose: str = Field(min_length=1)
    when_to_use: str = Field(min_length=1)
    steps: List[str] = []
    template_ref: Optional[str] = Field(default=None, max_length=200)
    pitfalls: Optional[str] = None
    scenario_codes: List[str] = []
    not_applicable_when: Optional[str] = None
    prerequisites: Optional[str] = None
    verification_standard: Optional[str] = None
    difficulty: ToolDifficulty = ToolDifficulty.MEDIUM
    typical_duration: Optional[str] = Field(default=None, max_length=32)
    owner_user_id: Optional[int] = None


class ToolUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    alias: Optional[str] = Field(default=None, max_length=96)
    category: Optional[ToolCategory] = None
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)
    purpose: Optional[str] = None
    when_to_use: Optional[str] = None
    steps: Optional[List[str]] = None
    template_ref: Optional[str] = Field(default=None, max_length=200)
    pitfalls: Optional[str] = None
    scenario_codes: Optional[List[str]] = None
    not_applicable_when: Optional[str] = None
    prerequisites: Optional[str] = None
    verification_standard: Optional[str] = None
    difficulty: Optional[ToolDifficulty] = None
    typical_duration: Optional[str] = Field(default=None, max_length=32)
    owner_user_id: Optional[int] = None
    is_active: Optional[bool] = None


class ToolReviewRequest(BaseModel):
    decision: str = Field(pattern="^(APPROVE|REJECT)$")
    note: Optional[str] = Field(default=None, max_length=500)


class ToolCategoryGroup(BaseModel):
    category: str
    label: str
    count: int
    tools: List[ToolOut] = []


class ToolMatchRequest(BaseModel):
    problem: Optional[str] = Field(
        default=None, max_length=500, description="用一句话描述问题；只按场景筛选时可留空"
    )
    scenario_codes: List[str] = []
    category_filters: List[str] = []
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)
    step_no: Optional[str] = None
    sort: str = Field(default="fit", pattern="^(fit|difficulty|duration|usage)$")
    limit: int = Field(default=8, ge=1, le=33)


class ToolMatchHit(BaseModel):
    tool: ToolOut
    score: float
    match_level: str = "mid"
    matched_on: List[str] = Field(description="命中的场景/关键词/步骤")
    why: Optional[str] = None
    verification_standard: Optional[str] = None
    usage: ToolUsageSummary = ToolUsageSummary()


class ToolMatchResponse(BaseModel):
    problem: Optional[str] = None
    scenario_codes: List[str] = []
    hits: List[ToolMatchHit]
    hint: str


class ToolMetaOut(BaseModel):
    category_labels: dict
    level_labels: dict
    difficulty_labels: dict
    scenarios: List[KnowledgeScenarioOut] = []
