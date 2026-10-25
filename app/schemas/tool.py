"""工具箱出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
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
    is_active: bool = True


class ToolWorkflowStepOut(BaseModel):
    step_no: str
    name: str
    stage_no: int


class ToolUsageSummary(BaseModel):
    used: int = 0
    effective: int = 0
    rate: Optional[float] = None


class ToolDetailOut(ToolOut):
    usage: ToolUsageSummary = ToolUsageSummary()
    knowledge: List[KnowledgeBrief] = []
    workflow_steps: List[ToolWorkflowStepOut] = []


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
