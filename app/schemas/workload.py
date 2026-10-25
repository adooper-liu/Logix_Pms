"""工作量与产能出入参。"""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import WorkMeasurementSource
from app.schemas.common import ORMModel


class WorkMeasurementStandardCreate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: str = Field(max_length=160)
    activity_id: int
    task_id: Optional[int] = None
    position_id: int
    org_unit_id: Optional[int] = None

    method_description: Optional[str] = None
    source: WorkMeasurementSource = WorkMeasurementSource.TIME_STUDY
    observed_minutes: float = Field(gt=0, description="观测到的平均作业时间（分钟）")
    rating_factor: float = Field(default=1.0, ge=0.5, le=2.0, description="评定系数")
    allowance_rate: float = Field(default=0.0, ge=0, le=1, description="宽放率 0–1")
    sample_size: int = Field(default=0, ge=0)
    monthly_frequency: float = Field(default=0.0, ge=0, description="计划频次（次/月）")

    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    note: Optional[str] = None


class WorkMeasurementStandardUpdate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=48)
    name: Optional[str] = Field(default=None, max_length=160)
    activity_id: Optional[int] = None
    task_id: Optional[int] = None
    position_id: Optional[int] = None
    org_unit_id: Optional[int] = None
    method_description: Optional[str] = None
    source: Optional[WorkMeasurementSource] = None
    observed_minutes: Optional[float] = Field(default=None, gt=0)
    rating_factor: Optional[float] = Field(default=None, ge=0.5, le=2.0)
    allowance_rate: Optional[float] = Field(default=None, ge=0, le=1)
    sample_size: Optional[int] = Field(default=None, ge=0)
    monthly_frequency: Optional[float] = Field(default=None, ge=0)
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    note: Optional[str] = None


class WorkMeasurementStandardOut(ORMModel):
    id: int
    code: str
    name: str
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    task_id: Optional[int] = None
    task_code: Optional[str] = None
    task_name: Optional[str] = None
    position_id: int
    position_name: Optional[str] = None
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None

    method_description: Optional[str] = None
    source: str
    source_label: str
    observed_minutes: float
    rating_factor: float
    allowance_rate: float
    standard_minutes: float
    sample_size: int
    monthly_frequency: float
    demand_minutes: float = Field(description="standard_minutes × monthly_frequency")

    status: str
    status_label: str
    version: int
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    note: Optional[str] = None
    verified_by_id: Optional[int] = None
    verified_by_name: Optional[str] = None
    verified_at: Optional[UtcDateTime] = None
    observation_count: int = 0
    reviewed_by_id: Optional[int] = None
    reviewed_by_name: Optional[str] = None
    reviewed_at: Optional[UtcDateTime] = None
    review_note: Optional[str] = None
    created_at: UtcDateTime


class WorkMeasurementObservationCreate(BaseModel):
    observed_minutes: float = Field(gt=0, description="本次观测到的作业时间（分钟）")
    observed_at: Optional[datetime] = None
    note: Optional[str] = None


class WorkMeasurementObservationOut(ORMModel):
    id: int
    standard_id: int
    sequence: int
    observed_minutes: float
    observed_at: UtcDateTime
    observer_user_id: Optional[int] = None
    observer_name: Optional[str] = None
    note: Optional[str] = None
    created_at: UtcDateTime


class WorkMeasurementReviewIn(BaseModel):
    approved: bool
    note: Optional[str] = Field(default=None, max_length=400)


class CapacityCalendarCreate(BaseModel):
    org_unit_id: int
    position_id: int
    period: date
    headcount: float = Field(default=0, ge=0)
    available_hours_per_person: float = Field(default=0, ge=0)
    attendance_rate: float = Field(default=1.0, ge=0, le=1)
    equipment_availability: float = Field(default=1.0, ge=0, le=1)
    note: Optional[str] = None


class CapacityCalendarUpdate(BaseModel):
    headcount: Optional[float] = Field(default=None, ge=0)
    available_hours_per_person: Optional[float] = Field(default=None, ge=0)
    attendance_rate: Optional[float] = Field(default=None, ge=0, le=1)
    equipment_availability: Optional[float] = Field(default=None, ge=0, le=1)
    note: Optional[str] = None


class CapacityCalendarOut(ORMModel):
    id: int
    org_unit_id: int
    org_unit_name: Optional[str] = None
    position_id: int
    position_name: Optional[str] = None
    period: date
    headcount: float
    available_hours_per_person: float
    attendance_rate: float
    equipment_availability: float
    available_minutes: float
    note: Optional[str] = None
    created_at: UtcDateTime


class WorkloadStandardRow(BaseModel):
    standard_id: int
    code: str
    name: str
    activity_id: int
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    position_id: int
    position_name: Optional[str] = None
    standard_minutes: float
    monthly_frequency: float
    demand_minutes: float
    sample_size: int = 0
    observation_count: int = 0
    observed_minutes: float = 0
    review_note: Optional[str] = None
    reviewed_by_name: Optional[str] = None
    status: str
    status_label: str
    source: str
    source_label: str
    included: bool = Field(description="只有 VERIFIED 计入产能与成本口径")


class WorkloadActualRow(BaseModel):
    activity_id: Optional[int] = None
    activity_code: Optional[str] = None
    activity_name: Optional[str] = None
    position_id: Optional[int] = None
    position_name: Optional[str] = None
    task_count: int = 0
    effort_minutes: float = 0


class WorkloadCapacityRow(BaseModel):
    capacity_id: int
    org_unit_id: int
    org_unit_name: Optional[str] = None
    position_id: int
    position_name: Optional[str] = None
    period: date
    headcount: float
    available_minutes: float
    demand_minutes: float
    gap_minutes: float
    utilization: Optional[float] = Field(
        default=None, description="需求工时 ÷ 可用工时；无可用工时为 null"
    )


class WorkloadTotals(BaseModel):
    demand_minutes: float = 0
    available_minutes: float = 0
    actual_minutes: float = 0
    utilization: Optional[float] = None


class WorkloadSummaryOut(BaseModel):
    period: date
    standards: List[WorkloadStandardRow] = []
    actual: List[WorkloadActualRow] = []
    capacity: List[WorkloadCapacityRow] = []
    totals: WorkloadTotals = WorkloadTotals()


class WorkloadMetaOut(BaseModel):
    source_labels: dict
    status_labels: dict
    boundary_note: str = ""
