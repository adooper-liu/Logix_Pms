"""CSV 事件日志导入契约。"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel

from app.core.timeutil import UtcDateTime


class LogActivityLabelOut(BaseModel):
    label: str
    count: int
    mapped_activity_id: Optional[int] = None
    mapped_activity_code: Optional[str] = None
    mapped_activity_name: Optional[str] = None
    suggested_activity_id: Optional[int] = None
    suggested_activity_code: Optional[str] = None
    suggested_activity_name: Optional[str] = None
    suggestion_reason: Optional[str] = None


class LogImportOut(BaseModel):
    id: int
    process_id: int
    file_name: str
    status: str
    row_count: int
    case_count: int
    window_start: Optional[UtcDateTime] = None
    window_end: Optional[UtcDateTime] = None
    labels: List[LogActivityLabelOut] = []
    metrics: Dict[str, Any] = {}
    claim_id: Optional[int] = None
    created_at: Optional[UtcDateTime] = None
    committed_at: Optional[UtcDateTime] = None


class LogImportMapIn(BaseModel):
    mapping: Dict[str, Optional[int]] = {}


class LogComparisonMetricOut(BaseModel):
    before: Optional[float] = None
    after: Optional[float] = None
    delta: Optional[float] = None
    delta_pct: Optional[float] = None


class LogComparisonOut(BaseModel):
    process_id: int
    before: LogImportOut
    after: LogImportOut
    comparable: bool
    reasons: List[str] = []
    warnings: List[str] = []
    metrics: Dict[str, LogComparisonMetricOut] = {}
    variants: Dict[str, List[Dict[str, Any]]] = {}
    conclusion: str


class LogComparisonReceiptIn(BaseModel):
    before_id: int
    after_id: int
    decision: Literal["ACCEPT", "RETURN", "OBSERVE"]
    rationale: str


class LogComparisonReceiptOut(BaseModel):
    id: int
    process_id: int
    before_import_id: int
    after_import_id: int
    decision: str
    rationale: str
    comparable: bool
    sample_ok: bool
    claim_allowed: bool
    metrics: Dict[str, Any] = {}
    conclusion: Optional[str] = None
    accepted_by_name: Optional[str] = None
    accepted_at: Optional[UtcDateTime] = None
    created_at: Optional[UtcDateTime] = None


class ComparisonClaimReadinessOut(BaseModel):
    process_id: int
    before_import_id: int
    after_import_id: int
    claim_allowed: bool
    reasons: List[str] = []
    latest_receipt: Optional[LogComparisonReceiptOut] = None


class ComparisonReceiptOptionOut(BaseModel):
    receipt_id: int
    before_import_id: int
    after_import_id: int
    before_file_name: str
    after_file_name: str
    mean_before: Optional[float] = None
    mean_after: Optional[float] = None
    delta_pct: Optional[float] = None
    case_count_before: Optional[int] = None
    case_count_after: Optional[int] = None
    accepted_by_name: Optional[str] = None
    accepted_at: Optional[UtcDateTime] = None


class LogComparisonWriteBackOption(BaseModel):
    kpi_id: int
    code: str
    name: str
    unit: Optional[str] = None
    direction: str
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    observed_value: float
    observed_period: date


class LogComparisonWriteBackOptionsOut(BaseModel):
    process_id: int
    before_import_id: int
    after_import_id: int
    claim_allowed: bool
    reasons: List[str] = []
    latest_receipt_id: Optional[int] = None
    kpis: List[LogComparisonWriteBackOption] = []
    note: str = ""


class LogComparisonWriteBackIn(BaseModel):
    before_id: int
    after_id: int
    kpi_id: int
    update_baseline: bool = True
    target_value: Optional[float] = None
    rationale: str


class LogComparisonWriteBackOut(BaseModel):
    process_id: int
    before_import_id: int
    after_import_id: int
    receipt_id: int
    kpi_id: int
    kpi_code: str
    kpi_unit: Optional[str] = None
    kpi_version_before: int
    kpi_version_after: int
    baseline_before: Optional[float] = None
    baseline_after: Optional[float] = None
    target_before: Optional[float] = None
    target_after: Optional[float] = None
    record_id: int
    record_period: date
    record_value: float
    record_revision: int
    claim_allowed: bool
    sample_ok: bool
