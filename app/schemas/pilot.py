"""十层单页出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime, UtcDateTimeIn
from app.models.enums import (
    PilotIssueStatus,
    PilotPathStatus,
    PilotPriority,
    PilotSeverity,
    PilotTaskStatus,
)
from app.schemas.common import ORMModel


class PilotMetaOut(BaseModel):
    path_status_labels: Dict[str, str]
    layer_status_labels: Dict[str, str]
    task_status_labels: Dict[str, str]
    issue_status_labels: Dict[str, str]
    priority_labels: Dict[str, str]
    severity_labels: Dict[str, str]
    applicability_labels: Dict[str, str]


class PilotLayerEvidenceOut(BaseModel):
    key: str
    label: str
    value: int
    required: bool
    met: bool
    applicability: str = "REQUIRED"
    applicability_label: str = ""
    applicability_reason: str = ""
    view: str = ""
    view_params: Dict[str, str] = Field(default_factory=dict)


class PilotActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None
    action: Optional[str] = None
    view_params: Dict[str, str] = Field(default_factory=dict)


class PilotDocumentOut(BaseModel):
    id: int
    code: str
    title: str
    category: str
    category_label: Optional[str] = None
    version_label: Optional[str] = None
    status_label: Optional[str] = None


class PilotRuleOut(BaseModel):
    id: int
    code: str
    title: str
    matter: str
    category: str
    category_label: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    approver: Optional[str] = None
    amount_limit: Optional[float] = None
    exception_path: Optional[str] = None
    evidence_required: Optional[str] = None


class PilotExceptionOut(BaseModel):
    id: int
    code: str
    title: str
    rule_code: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    expires_at: Optional[UtcDateTime] = None


class PilotLayerResourcesOut(BaseModel):
    documents: List[PilotDocumentOut] = []
    rules: List[PilotRuleOut] = []
    exceptions: List[PilotExceptionOut] = []


class PilotTaskOut(ORMModel):
    id: int
    layer_no: int
    title: str
    priority: str
    priority_label: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    due_date: Optional[date] = None
    acceptance: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    created_at: UtcDateTime
    completed_at: Optional[UtcDateTime] = None


class PilotIssueOut(ORMModel):
    id: int
    layer_no: int
    title: str
    severity: str
    severity_label: Optional[str] = None
    workaround: Optional[str] = None
    verification: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    due_date: Optional[date] = None
    status: str
    status_label: Optional[str] = None
    created_at: UtcDateTime
    closed_at: Optional[UtcDateTime] = None


class PilotLayerOut(ORMModel):
    layer_no: int
    title: str
    goal: str
    inputs: List[str] = []
    process: List[str] = []
    outputs: List[str] = []
    exit_criteria: str
    status: str
    status_label: str
    gate_open: bool
    current: bool
    context_summary: Optional[str] = None
    notes: Optional[str] = None
    evidence_items: List[PilotLayerEvidenceOut] = []
    applicability_revision: int = 0
    actions: List[PilotActionOut] = []
    resources: Optional[PilotLayerResourcesOut] = None
    tasks: List[PilotTaskOut] = []
    issues: List[PilotIssueOut] = []


class PilotPathOut(ORMModel):
    id: int
    name: str
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    current_layer: int
    current_layer_title: Optional[str] = None
    progress: float = 0.0
    baseline_version: str = "V0.1"
    draft_version: str = "V0.1"
    created_at: UtcDateTime
    updated_at: UtcDateTime
    layers: List[PilotLayerOut] = []


class PilotPathSummaryOut(ORMModel):
    id: int
    name: str
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    owner: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    current_layer: int
    current_layer_title: Optional[str] = None
    progress: float = 0.0
    updated_at: UtcDateTime


class PilotPathCreate(BaseModel):
    process_id: int
    name: Optional[str] = Field(default=None, max_length=160)
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)


class PilotPathUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    status: Optional[PilotPathStatus] = None
    owner_user_id: Optional[int] = None


class PilotApplicabilityIn(BaseModel):
    expected_revision: int = Field(ge=0)
    requirements: dict[str, dict[str, str]]


class PilotLayerUpdate(BaseModel):
    context_summary: Optional[str] = Field(default=None, max_length=400)
    notes: Optional[str] = None


class PilotTaskCreate(BaseModel):
    layer_no: int = Field(ge=1, le=10)
    title: str = Field(max_length=200)
    priority: PilotPriority = PilotPriority.MEDIUM
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    acceptance: Optional[str] = Field(default=None, max_length=400)


class PilotTaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    priority: Optional[PilotPriority] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    acceptance: Optional[str] = Field(default=None, max_length=400)
    status: Optional[PilotTaskStatus] = None


class PilotIssueCreate(BaseModel):
    layer_no: int = Field(ge=1, le=10)
    title: str = Field(max_length=200)
    severity: PilotSeverity = PilotSeverity.MAJOR
    workaround: Optional[str] = None
    verification: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None


class RpaIn(BaseModel):
    process_id: int
    activity_name: str = Field(max_length=200)
    bot_name: str = Field(max_length=200)
    manual_step: str
    owner_user_id: int


class TrainingIn(BaseModel):
    process_id: int
    trainee_user_id: int
    topic: str = Field(max_length=200)
    completed_on: date


class RecordSavedOut(BaseModel):
    id: int


class EventLogIn(BaseModel):
    process_id: int
    source_name: str = Field(max_length=80)
    case_key: str = Field(max_length=80)
    activity_name: str = Field(max_length=200)
    occurred_at: UtcDateTimeIn


class RpaRunIn(BaseModel):
    bot_id: int
    ran_at: UtcDateTimeIn
    outcome: str = Field(max_length=16)
    endpoint_id: int
    note: Optional[str] = None


class CaseIn(BaseModel):
    process_id: int
    title: str = Field(max_length=200)
    situation: str
    owner_user_id: int


class TechnologyUseIn(BaseModel):
    process_id: int
    kind: str = Field(max_length=16)
    name: str = Field(max_length=200)
    usage_note: str
    owner_user_id: int


class CodeLabelOut(BaseModel):
    code: str
    label: str


class RunBotOption(BaseModel):
    id: int
    bot_name: str
    activity_name: str


class RunEndpointOption(BaseModel):
    id: int
    name: str
    kind: str
    status_label: str


class RpaRunOptionsOut(BaseModel):
    bots: List[RunBotOption]
    endpoints: List[RunEndpointOption]
    outcomes: List[CodeLabelOut]


class PilotIssueUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    severity: Optional[PilotSeverity] = None
    workaround: Optional[str] = None
    verification: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    status: Optional[PilotIssueStatus] = None
