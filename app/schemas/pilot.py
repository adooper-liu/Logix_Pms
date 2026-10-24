"""十层单页出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
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


class PilotLayerEvidenceOut(BaseModel):
    key: str
    label: str
    value: int
    required: bool
    met: bool


class PilotActionOut(BaseModel):
    label: str
    view: str
    hint: Optional[str] = None
    action: Optional[str] = None


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
    actions: List[PilotActionOut] = []
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
    name: str = Field(max_length=160)
    process_id: int
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)


class PilotPathUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=160)
    status: Optional[PilotPathStatus] = None
    owner_user_id: Optional[int] = None


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


class PilotIssueUpdate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)
    severity: Optional[PilotSeverity] = None
    workaround: Optional[str] = None
    verification: Optional[str] = None
    owner_user_id: Optional[int] = None
    owner: Optional[str] = Field(default=None, max_length=64)
    due_date: Optional[date] = None
    status: Optional[PilotIssueStatus] = None
