"""流程项目 / 标准工作流 出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import Methodology, ProcessState, ProjectStatus, ScopeType, StepStatus
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- 标准工作流


class WorkflowStepOut(ORMModel):
    id: int
    stage_no: int
    step_no: str
    name: str
    action: str
    tools: str
    deliverables: str
    key_points: str
    is_mandatory: bool


class WorkflowStageOut(BaseModel):
    stage_no: int
    stage_name: str
    stage_goal: Optional[str] = None
    steps: List[WorkflowStepOut] = []


class ProjectStepOut(ORMModel):
    id: int
    project_id: int
    stage_no: int
    step_no: str
    name: str
    status: str
    owner: Optional[str] = None
    due_date: Optional[date] = None
    deliverable: Optional[str] = None
    notes: Optional[str] = None
    completed_at: Optional[UtcDateTime] = None
    is_milestone: bool = False


class ProjectStepUpdate(BaseModel):
    status: Optional[StepStatus] = None
    owner: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------- 项目


class ProjectBase(BaseModel):
    name: str = Field(max_length=160)
    methodology: Methodology
    status: ProjectStatus = ProjectStatus.PLANNING
    current_stage: int = Field(default=1, ge=1, le=5)
    priority: int = Field(default=3, ge=1, le=5, description="1 最高，5 最低")

    process_id: Optional[int] = None
    owner: str = Field(
        default="", max_length=64, description="展示用姓名；只传 owner_user_id 时由账号姓名填充"
    )
    owner_user_id: Optional[int] = Field(
        default=None, description="归属账号 id，权限判断以它为准；不传则按 owner 姓名尝试绑定"
    )
    sponsor: Optional[str] = None
    department: Optional[str] = None

    objective: Optional[str] = None
    scope: Optional[str] = None

    metric_name: Optional[str] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    metric_unit: Optional[str] = None

    budget: float = 0
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ProjectCreate(ProjectBase):
    code: Optional[str] = Field(default=None, description="不传则自动生成 PRJ-YYYY-NNN")
    seed_workflow: bool = Field(default=True, description="是否按标准工作流自动生成 24 个步骤")


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    methodology: Optional[Methodology] = None
    status: Optional[ProjectStatus] = None
    current_stage: Optional[int] = Field(default=None, ge=1, le=5)
    priority: Optional[int] = Field(default=None, ge=1, le=5)
    owner: Optional[str] = None
    owner_user_id: Optional[int] = Field(
        default=None, description="归属账号 id；显式传 null 表示解绑，仅改 owner 文本会重新尝试绑定"
    )
    sponsor: Optional[str] = None
    department: Optional[str] = None
    objective: Optional[str] = None
    scope: Optional[str] = None
    metric_name: Optional[str] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    metric_unit: Optional[str] = None
    improvement_pct: Optional[float] = None
    budget: Optional[float] = None
    actual_cost: Optional[float] = None
    roi_estimate: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    progress: Optional[float] = Field(default=None, ge=0, le=100)


class ProjectOut(ORMModel):
    id: int
    code: str
    name: str
    methodology: str
    methodology_label: Optional[str] = Field(
        default=None, description="中文标签，如「BPR 阶跃式重组」"
    )
    status: str
    status_label: Optional[str] = None
    current_stage: int
    stage_name: Optional[str] = None
    priority: int
    process_id: Optional[int] = None
    process_name: Optional[str] = None
    owner: str
    owner_user_id: Optional[int] = None
    sponsor: Optional[str] = None
    department: Optional[str] = None
    objective: Optional[str] = None
    scope: Optional[str] = None
    metric_name: Optional[str] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    metric_unit: Optional[str] = None
    improvement_pct: Optional[float] = None
    budget: float
    actual_cost: float
    roi_estimate: Optional[float] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    progress: float
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class StageProgress(BaseModel):
    stage_no: int
    stage_name: str
    total: int
    done: int
    progress: float


class NextAction(BaseModel):
    step_no: Optional[str] = None
    name: str
    stage_no: int
    suggestion: str


class ProjectDetail(BaseModel):
    project: ProjectOut
    stages: List[StageProgress]
    steps: List[ProjectStepOut]
    current_steps: List[ProjectStepOut] = Field(description="当前阶段未完成的步骤")
    next_action: Optional[NextAction] = None
    kpi_trend: List["ProjectKpiPoint"] = []


class ProjectKpiPoint(BaseModel):
    period: date
    value: float
    note: Optional[str] = None


ProjectDetail.model_rebuild()


# ---------------------------------------------------------------- 立项向导


class MethodologyRecommendRequest(BaseModel):
    process_state: ProcessState
    target_improvement_pct: float = Field(default=20, ge=0, le=100, description="目标改善幅度 %")
    scope: ScopeType = ScopeType.LOCAL
    involves_org_change: bool = Field(default=False, description="是否涉及组织/权责调整")
    data_available: bool = Field(default=False, description="是否有可用的流程数据/日志")
    duration_target_months: int = Field(default=6, ge=1, le=36)
    process_id: Optional[int] = None


class ToolRef(BaseModel):
    code: str
    name: str
    category: str
    stage_no: int


class PhasePlanItem(BaseModel):
    layer: str = Field(description="架构层 / 执行层 / 操作层")
    action: str


class MethodologyRecommendation(BaseModel):
    methodology: Methodology
    confidence: float = Field(ge=0, le=1, description="推荐置信度")
    headline: str
    rationale: List[str] = Field(description="判断依据")
    phase_plan: List[PhasePlanItem] = []
    recommended_tools: List[ToolRef] = []
    risks: List[str] = []
    alternatives: List[Methodology] = []


# ---------------------------------------------------------------- 甘特图与里程碑


class ScheduleStep(BaseModel):
    id: int
    step_no: str
    name: str
    status: str
    due_date: Optional[date] = None
    is_milestone: bool = False


class ScheduleStage(BaseModel):
    stage_no: int
    stage_name: str
    start: Optional[date] = None
    end: Optional[date] = None
    progress: float = 0.0
    done: int = 0
    total: int = 0
    steps: List[ScheduleStep] = []


class MilestoneItem(BaseModel):
    step_id: int
    stage_no: int
    step_no: str
    name: str
    due_date: Optional[date] = None
    status: str
    is_overdue: bool = False


class ProjectSchedule(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    owner: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    today: date
    total_days: Optional[int] = None
    elapsed_days: Optional[int] = None
    stages: List[ScheduleStage] = []
    milestones: List[MilestoneItem] = []
