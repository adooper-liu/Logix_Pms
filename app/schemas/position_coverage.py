"""岗位职责只读投影，来源与缺口不另存主数据。"""

from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.workload import WorkloadSummaryOut


class CoverageSourceOut(BaseModel):
    kind: str
    label: str
    id: Optional[int] = None
    node_key: Optional[str] = None


class CoverageRaciOut(BaseModel):
    id: int
    role_id: int
    role_name: str
    raci: str
    raci_label: str
    scope_key: str
    node_key: Optional[str] = None
    activity_id: Optional[int] = None


class CoverageGapOut(BaseModel):
    code: str
    message: str
    process_id: Optional[int] = None
    activity_id: Optional[int] = None
    role_id: Optional[int] = None
    node_key: Optional[str] = None


class CoverageActivityOut(BaseModel):
    process_id: int
    process_code: str
    process_name: str
    activity_id: int
    activity_code: str
    activity_name: str
    node_keys: list[str] = Field(default_factory=list)
    model_version_id: Optional[int] = None
    model_status: str = "UNVERSIONED"
    binding_consistency: str = "PENDING_CONFIRM"
    sources: list[CoverageSourceOut] = Field(default_factory=list)
    raci: list[CoverageRaciOut] = Field(default_factory=list)
    standard_ids: list[int] = Field(default_factory=list)
    designer_url: str


class CoverageProcessOut(BaseModel):
    id: int
    code: str
    name: str
    model_version_id: Optional[int] = None
    model_status: str


class PositionCoverageOut(BaseModel):
    position_id: int
    code: str
    name: str
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    is_active: bool
    period: date
    processes: list[CoverageProcessOut] = Field(default_factory=list)
    activities: list[CoverageActivityOut] = Field(default_factory=list)
    unmapped_roles: list[CoverageGapOut] = Field(default_factory=list)
    matter_assignments: list[CoverageRaciOut] = Field(default_factory=list)
    workload: WorkloadSummaryOut
    gaps: list[CoverageGapOut] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
