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
    purpose: str = Field(
        default="STAGE_GATE",
        pattern="^(STAGE_GATE|DATA_READY|GO_LIVE_READY|RUN_EFFECTIVE|IMPROVEMENT_MET)$",
    )
    round_id: Optional[int] = Field(default=None, ge=1)
    expected_revision: Optional[int] = Field(default=None, ge=0)
    project_id: int
    stage_no: int = Field(ge=1, le=5)
    gate_code: str = Field(default="STAGE_GATE", max_length=32)
    exit_criteria: Optional[str] = None
    evidence_url: str = Field(min_length=1, max_length=500)
    conclusion: GateConclusion
    # 声明本次门禁依据改善对照时，必须引用已接收且达到样本/可比条件的对照。
    claims_improvement: bool = False
    comparison_receipt_id: Optional[int] = Field(default=None, ge=1)
    note: Optional[str] = None


class GateAttestationOut(ORMModel):
    purpose: str = "STAGE_GATE"
    round_id: Optional[int] = None
    evidence_snapshot: Optional[dict] = None
    claims_improvement: bool = False
    comparison_receipt_id: Optional[int] = None
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
