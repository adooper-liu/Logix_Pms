"""战略目标与承接关系出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime
from app.models.enums import StrategyPeriod, StrategyStatus
from app.schemas.common import ORMModel


class StrategyObjectiveCreate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    name: str = Field(max_length=160)
    description: Optional[str] = None
    year: int = Field(ge=2000, le=2100)
    period: StrategyPeriod = StrategyPeriod.ANNUAL
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=24)
    source_document: Optional[str] = Field(default=None, max_length=200)
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    status: StrategyStatus = StrategyStatus.ACTIVE


class StrategyObjectiveUpdate(BaseModel):
    code: Optional[str] = Field(default=None, max_length=32)
    name: Optional[str] = Field(default=None, max_length=160)
    description: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=2000, le=2100)
    period: Optional[StrategyPeriod] = None
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = Field(default=None, max_length=24)
    source_document: Optional[str] = Field(default=None, max_length=200)
    owner: Optional[str] = Field(default=None, max_length=64)
    owner_user_id: Optional[int] = None
    status: Optional[StrategyStatus] = None


class ObjectiveLinkCreate(BaseModel):
    process_id: int
    kpi_id: Optional[int] = Field(default=None, description="可选：把目标承接落到具体 KPI")
    note: Optional[str] = Field(default=None, max_length=200)


class ObjectiveLinkOut(BaseModel):
    id: int
    process_id: int
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    process_level: Optional[int] = None
    kpi_id: Optional[int] = None
    kpi_code: Optional[str] = None
    kpi_name: Optional[str] = None
    note: Optional[str] = None


class StrategyObjectiveOut(ORMModel):
    id: int
    code: str
    name: str
    description: Optional[str] = None
    year: int
    period: str
    period_label: str
    baseline_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    source_document: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    status: str
    status_label: str
    links: List[ObjectiveLinkOut] = []
    process_count: int = 0
    kpi_count: int = 0
    created_at: UtcDateTime
    updated_at: UtcDateTime


class StrategyMetaOut(BaseModel):
    period_labels: dict
    status_labels: dict


class StrategySummaryOut(BaseModel):
    year: int
    objective_count: int
    active_count: int
    archived_count: int
    linked_count: int
    unlinked_count: int
    kpi_link_count: int
