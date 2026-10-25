"""成熟度评估与阶段门禁出入参。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import GateConclusion, MaturityDimension
from app.schemas.common import ORMModel


class MaturityMetaOut(BaseModel):
    dimension_labels: Dict[str, str]
    conclusion_labels: Dict[str, str]


class MaturityAssessmentCreate(BaseModel):
    process_id: int
    org_unit_id: Optional[int] = None
    dimension: MaturityDimension
    level: int = Field(ge=0, le=5)
    evidence_url: str = Field(min_length=1, max_length=500)
    valid_until: Optional[date] = None
    note: Optional[str] = None


class MaturityAssessmentOut(ORMModel):
    id: int
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    dimension: str
    dimension_label: Optional[str] = None
    level: int
    evidence_url: str
    assessed_by_user_id: Optional[int] = None
    assessed_by: Optional[str] = None
    assessed_at: UtcDateTime
    valid_until: Optional[date] = None
    note: Optional[str] = None


class GateAttestationCreate(BaseModel):
    project_id: int
    stage_no: int = Field(ge=1, le=5)
    gate_code: str = Field(default="STAGE_GATE", max_length=32)
    exit_criteria: Optional[str] = None
    evidence_url: str = Field(min_length=1, max_length=500)
    conclusion: GateConclusion
    note: Optional[str] = None


class GateAttestationOut(ORMModel):
    id: int
    project_id: int
    project_code: Optional[str] = None
    stage_no: int
    gate_code: str
    exit_criteria: Optional[str] = None
    evidence_url: str
    conclusion: str
    conclusion_label: Optional[str] = None
    signed_by_user_id: Optional[int] = None
    signed_by: Optional[str] = None
    signed_at: UtcDateTime
    note: Optional[str] = None


class CoverageRowOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    l4_total: int
    l4_with_owner: int
    l4_with_document: int
    l4_with_kpi: int
    owner_coverage_pct: float
    document_coverage_pct: float
    kpi_coverage_pct: float


class CoverageSummaryOut(BaseModel):
    rows: List[CoverageRowOut] = []
    l4_total: int = 0
    l4_with_owner: int = 0
    l4_with_document: int = 0
    l4_with_kpi: int = 0
