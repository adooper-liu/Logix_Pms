"""P3b 关键过程覆盖度矩阵的只读契约。"""

from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel

from app.core.timeutil import UtcDateTime


class CoverageGapOut(BaseModel):
    code: str
    message: str
    targets: List[str] = []


class CoverageProcessOut(BaseModel):
    id: int
    code: str
    name: str


class CoverageImplementationOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    node_key: str
    node_name: Optional[str] = None
    relation: str
    relation_label: str
    coverage: float = 1.0
    model_version_id: Optional[int] = None
    source_model_version_ids: List[Optional[int]] = []
    current: bool = False
    historical: bool = False
    legacy: bool = False
    source_note: Optional[str] = None
    source_label: str


class UnmodeledCoverageOut(BaseModel):
    id: int
    process_id: int
    model_version_id: Optional[int] = None
    reason: str
    source_ref: Optional[str] = None


class GapOwnerPositionOut(BaseModel):
    id: Optional[int] = None
    code: Optional[str] = None
    name: Optional[str] = None
    source: List[str] = []
    mapped: bool = False


class BoundaryLineOut(BaseModel):
    child_id: int
    child_code: str
    child_name: str
    starts_at: str
    ends_at: str
    in_scope: str
    out_of_scope: str
    distinct_work: str


class BoundaryReviewOut(BaseModel):
    parent_id: int
    code: str
    name: str
    status: str
    status_label: str
    overlap_found: Optional[bool] = None
    overlap_work: Optional[str] = None
    note: Optional[str] = None
    line_complete: bool = False
    line_complete_label: str
    lines: List[BoundaryLineOut] = []


class KeyActivityCoverageOut(BaseModel):
    id: int
    code: str
    name: str
    parent_id: Optional[int] = None
    key_basis: Optional[str] = None
    key_basis_source: str
    coverage_status: str
    coverage_status_label: str
    implementations: List[CoverageImplementationOut] = []
    unmodeled: List[UnmodeledCoverageOut] = []
    duplicate_processes: List[CoverageProcessOut] = []
    gap_owner_positions: List[GapOwnerPositionOut] = []
    gaps: List[CoverageGapOut] = []


class CoverageSummaryOut(BaseModel):
    key_activities: int = 0
    implemented: int = 0
    unmodeled: int = 0
    uncovered: int = 0
    multi_process: int = 0
    unreviewed: int = 0
    evidence_incomplete: int = 0
    invalid_key_basis: int = 0
    invalid_hierarchy: int = 0


class KeyProcessCoverageOut(BaseModel):
    generated_at: UtcDateTime
    summary: CoverageSummaryOut
    activities: List[KeyActivityCoverageOut] = []
    boundary_reviews: List[BoundaryReviewOut] = []
    labels: Dict[str, Dict[str, str]] = {}

    model_config = {"from_attributes": True}
