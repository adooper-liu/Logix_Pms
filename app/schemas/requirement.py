"""客户/市场要求与目标承接工作台契约。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime

SOURCE_TYPE_LABELS: Dict[str, str] = {
    "CUSTOMER": "客户要求",
    "MARKET": "市场要求",
    "REGULATION": "合规要求",
    "OTHER": "其他",
}


class RequirementObjectiveOut(BaseModel):
    id: int
    code: str
    name: str


class RequirementIn(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    source_type: Literal["CUSTOMER", "MARKET", "REGULATION", "OTHER"]
    title: str = Field(max_length=160)
    requirement: str
    evidence_url: Optional[str] = Field(default=None, max_length=500)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    objective_ids: List[int] = []


class RequirementUpdate(BaseModel):
    source_type: Optional[Literal["CUSTOMER", "MARKET", "REGULATION", "OTHER"]] = None
    title: Optional[str] = Field(default=None, max_length=160)
    requirement: Optional[str] = None
    evidence_url: Optional[str] = Field(default=None, max_length=500)
    status: Optional[Literal["ACTIVE", "CLOSED"]] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    objective_ids: Optional[List[int]] = None


class RequirementOut(BaseModel):
    id: int
    code: str
    source_type: str
    source_label: str
    title: str
    requirement: str
    evidence_url: Optional[str] = None
    status: str
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    objectives: List[RequirementObjectiveOut] = []
    created_at: Optional[UtcDateTime] = None
    updated_at: Optional[UtcDateTime] = None


class AlignmentProcessOut(BaseModel):
    id: int
    code: str
    name: str
    level: int


class AlignmentKpiOut(BaseModel):
    id: int
    code: str
    name: str
    unit: Optional[str] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    has_measurement: bool = False
    has_latest_record: bool = False


class AlignmentEnablerOut(BaseModel):
    key: str
    label: str
    ready: bool
    metrics: Dict[str, Any] = {}
    metric_labels: Dict[str, str] = {}
    gaps: List[str] = []
    next_action: str
    next_view: Optional[str] = None
    next_params: Dict[str, Any] = {}


class AlignmentObjectiveOut(BaseModel):
    id: int
    code: str
    name: str
    year: int
    owner: Optional[str] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    status: str
    requirements: List[RequirementObjectiveOut] = []
    processes: List[AlignmentProcessOut] = []
    kpis: List[AlignmentKpiOut] = []
    enablers: List[AlignmentEnablerOut] = []
    gaps: List[str] = []


class AlignmentOut(BaseModel):
    year: int
    source_labels: Dict[str, str] = SOURCE_TYPE_LABELS
    enabler_labels: Dict[str, str] = {}
    requirements: List[RequirementOut] = []
    objectives: List[AlignmentObjectiveOut] = []
    summary: Dict[str, Any] = {}
