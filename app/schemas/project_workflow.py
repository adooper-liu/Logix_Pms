"""五阶段工作台出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.schemas.evidence import ProjectEvidenceClaimOut


class WorkbenchStepOut(BaseModel):
    id: int
    stage_no: int
    step_no: str
    name: str
    status: str
    status_label: str
    goal: Optional[str] = None
    inputs: List[str] = []
    process_steps: List[str] = []
    output: Optional[str] = None
    evidence: List[str] = []
    owner: Optional[str] = None
    next_action: Optional[str] = None
    tools: List[str] = []
    receiver: Optional[str] = None
    verified_by: Optional[str] = None
    verified_at: Optional[UtcDateTime] = None
    blocked_reason: Optional[str] = None
    blocked_owner: Optional[str] = None
    blocked_due: Optional[date] = None
    decision_options: List[str] = []
    decision_maker: Optional[str] = None
    decision_due: Optional[date] = None
    due_date: Optional[date] = None
    updated_at: Optional[UtcDateTime] = None


class GateConditionOut(BaseModel):
    id: int
    stage_no: int
    condition_code: Optional[str] = None
    text: str
    evidence: Optional[str] = None
    owner: Optional[str] = None
    due_date: Optional[date] = None
    is_met: bool = False
    is_critical: bool = True
    note: Optional[str] = None
    met_at: Optional[UtcDateTime] = None
    met_by: Optional[str] = None


class WorkbenchStageOut(BaseModel):
    stage_no: int
    name: str
    status: str  # complete / current / locked
    status_label: str
    goal: Optional[str] = None
    summary: Optional[str] = None
    step_count: int = 0
    done_count: int = 0


class WorkbenchGateOut(BaseModel):
    conditions: List[GateConditionOut] = []
    met_count: int = 0
    total: int = 0
    can_advance: bool = False
    block_reasons: List[str] = []


class WorkbenchContextOut(BaseModel):
    stage_no: Optional[int] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    items: List[str] = []


class WorkbenchProjectOut(BaseModel):
    id: int
    code: str
    name: str
    owner: str
    status: str
    status_label: str
    current_stage: int
    objective: Optional[str] = None


class WorkbenchLinkOut(BaseModel):
    project: str
    ten_layer: str
    stage: str


class WorkbenchOut(BaseModel):
    project: WorkbenchProjectOut
    stages: List[WorkbenchStageOut] = []
    current_stage: Optional[WorkbenchStageOut] = None
    viewing_stage: int = 1
    read_only: bool = False
    steps: List[WorkbenchStepOut] = []
    claims: List[ProjectEvidenceClaimOut] = []
    evidence_level_labels: Dict[str, str] = {}
    evidence_verdict_labels: Dict[str, str] = {}
    gate: WorkbenchGateOut = WorkbenchGateOut()
    previous: WorkbenchContextOut = WorkbenchContextOut()
    next: WorkbenchContextOut = WorkbenchContextOut()
    links: WorkbenchLinkOut
    step_status_labels: Dict[str, str] = {}
    stage_status_labels: Dict[str, str] = {}
    hint: str = ""


class StepUpdateIn(BaseModel):
    status: Optional[str] = Field(
        default=None,
        pattern="^(PENDING|IN_PROGRESS|PENDING_VERIFY|DONE|BLOCKED|DECISION|SKIPPED)$",
    )
    goal: Optional[str] = None
    inputs: Optional[List[str]] = None
    process_steps: Optional[List[str]] = None
    output: Optional[str] = None
    evidence: Optional[List[str]] = None
    owner: Optional[str] = None
    next_action: Optional[str] = None
    receiver: Optional[str] = None
    verified_by: Optional[str] = None
    blocked_reason: Optional[str] = None
    blocked_owner: Optional[str] = None
    blocked_due: Optional[date] = None
    decision_options: Optional[List[str]] = None
    decision_maker: Optional[str] = None
    decision_due: Optional[date] = None
    due_date: Optional[date] = None
    note: Optional[str] = None


class GateConditionUpdateIn(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=240)
    evidence: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    is_met: Optional[bool] = None
    is_critical: Optional[bool] = None
    note: Optional[str] = None


class GateConditionCreateIn(BaseModel):
    stage_no: int = Field(ge=1, le=5)
    text: str = Field(min_length=1, max_length=240)
    evidence: Optional[str] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    is_critical: bool = True
    sort_order: int = 99


class AdvanceResultOut(BaseModel):
    current_stage: int
    status: str
    status_label: str
    message: str
