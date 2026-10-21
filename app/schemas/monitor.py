"""运营监控出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime, UtcDateTimeIn
from app.models.enums import ExceptionSeverity, ExceptionStatus, KpiDimension, KpiDirection
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- KPI


class KpiDefinitionCreate(BaseModel):
    code: str = Field(max_length=32)
    name: str = Field(max_length=64)
    dimension: KpiDimension
    direction: KpiDirection = KpiDirection.LOWER_BETTER
    unit: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    description: Optional[str] = None
    process_id: Optional[int] = None
    owner: Optional[str] = None


class KpiRecordCreate(BaseModel):
    period: date
    value: float
    project_id: Optional[int] = None
    note: Optional[str] = None


class KpiRecordOut(ORMModel):
    id: int
    kpi_id: int
    period: date
    value: float
    note: Optional[str] = None


class KpiDefinitionOut(ORMModel):
    id: int
    code: str
    name: str
    dimension: str
    direction: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    description: Optional[str] = None
    process_id: Optional[int] = None
    owner: Optional[str] = None
    is_active: bool
    latest_value: Optional[float] = None
    achievement_rate: Optional[float] = Field(default=None, description="当前值对目标值的达成率 %")
    trend: Optional[str] = Field(default=None, description="UP / DOWN / FLAT")


class RadarDimension(BaseModel):
    dimension: str
    label: str
    kpi_count: int
    achievement_rate: float = Field(description="该维度平均达成率 %")
    status: str = Field(description="GOOD / WATCH / RISK")


class KpiTrendPoint(BaseModel):
    period: date
    value: float


class KpiTrendSeries(BaseModel):
    kpi_id: int
    code: str
    name: str
    dimension: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    direction: str
    points: List[KpiTrendPoint] = []


class KpiRadarResponse(BaseModel):
    overall_achievement: float
    dimensions: List[RadarDimension]
    series: List[KpiTrendSeries] = []


# ---------------------------------------------------------------- 异常事件


class ExceptionCreate(BaseModel):
    title: str = Field(max_length=160)
    description: Optional[str] = None
    severity: ExceptionSeverity = ExceptionSeverity.MEDIUM
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = Field(
        default=None, description="责任账号 id，权限判断以它为准；不传则按 owner 姓名尝试绑定"
    )
    due_at: Optional[UtcDateTimeIn] = None


class ExceptionUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[ExceptionSeverity] = None
    status: Optional[ExceptionStatus] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = Field(
        default=None, description="责任账号 id；显式传 null 表示解绑，仅改 owner 文本会重新尝试绑定"
    )
    due_at: Optional[UtcDateTimeIn] = None
    root_cause: Optional[str] = None
    action_taken: Optional[str] = None


class ExceptionOut(ORMModel):
    id: int
    code: str
    title: str
    description: Optional[str] = None
    severity: str
    status: str
    process_id: Optional[int] = None
    project_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    detected_at: UtcDateTime
    due_at: Optional[UtcDateTime] = None
    resolved_at: Optional[UtcDateTime] = None
    closed_at: Optional[UtcDateTime] = None
    root_cause: Optional[str] = None
    action_taken: Optional[str] = None
    is_overdue: bool = False


class ExceptionSummary(BaseModel):
    total: int
    open: int
    in_progress: int
    resolved: int
    closed: int
    overdue: int
    by_severity: dict
