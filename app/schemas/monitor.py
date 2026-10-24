"""运营监控出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel, Field

from app.core.timeutil import UtcDateTime, UtcDateTimeIn
from app.models.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    KpiDimension,
    KpiDirection,
    KpiFrequency,
    KpiKind,
)
from app.schemas.common import ORMModel

# ---------------------------------------------------------------- KPI


class KpiDefinitionCreate(BaseModel):
    code: str = Field(max_length=32)
    name: str = Field(max_length=64)
    dimension: KpiDimension
    kind: KpiKind = KpiKind.PROCESS
    direction: KpiDirection = KpiDirection.LOWER_BETTER
    unit: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    description: Optional[str] = None

    # 定义卡：口径、粒度、来源与质量规则
    formula: Optional[str] = None
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    granularity: Optional[str] = None
    frequency: KpiFrequency = KpiFrequency.MONTHLY
    source_system: Optional[str] = None
    quality_rule: Optional[str] = None

    # 红/黄/绿三条线
    red_threshold: Optional[float] = None
    yellow_threshold: Optional[float] = None
    green_threshold: Optional[float] = None

    process_id: Optional[int] = None
    activity_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None


class KpiDefinitionUpdate(BaseModel):
    """局部更新；只改传了的字段。定义口径变更会让 version +1。"""

    code: Optional[str] = Field(default=None, max_length=32)
    name: Optional[str] = Field(default=None, max_length=64)
    dimension: Optional[KpiDimension] = None
    kind: Optional[KpiKind] = None
    direction: Optional[KpiDirection] = None
    unit: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    description: Optional[str] = None

    formula: Optional[str] = None
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    granularity: Optional[str] = None
    frequency: Optional[KpiFrequency] = None
    source_system: Optional[str] = None
    quality_rule: Optional[str] = None

    red_threshold: Optional[float] = None
    yellow_threshold: Optional[float] = None
    green_threshold: Optional[float] = None

    process_id: Optional[int] = None
    activity_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: Optional[bool] = None


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
    kind: str
    kind_label: str
    direction: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    baseline_value: Optional[float] = None
    description: Optional[str] = None

    formula: Optional[str] = None
    numerator: Optional[str] = None
    denominator: Optional[str] = None
    granularity: Optional[str] = None
    frequency: str
    frequency_label: str
    source_system: Optional[str] = None
    quality_rule: Optional[str] = None

    red_threshold: Optional[float] = None
    yellow_threshold: Optional[float] = None
    green_threshold: Optional[float] = None

    process_id: Optional[int] = None
    activity_id: Optional[int] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None
    version: int
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    is_active: bool

    latest_value: Optional[float] = None
    achievement_rate: Optional[float] = Field(default=None, description="当前值对目标值的达成率 %")
    trend: Optional[str] = Field(default=None, description="UP / DOWN / FLAT")
    status: Optional[str] = Field(default=None, description="RED / YELLOW / GREEN")
    status_label: Optional[str] = None


class KpiMetaOut(BaseModel):
    kind_labels: dict
    frequency_labels: dict
    status_labels: dict
    dimension_labels: dict


class KpiKindSummary(BaseModel):
    kind: str
    label: str
    kpi_count: int
    red: int = 0
    yellow: int = 0
    green: int = 0
    gray: int = 0


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
    kind: str
    kind_label: str
    unit: Optional[str] = None
    target_value: Optional[float] = None
    direction: str
    frequency: str
    granularity: Optional[str] = None
    status: Optional[str] = None
    status_label: Optional[str] = None
    points: List[KpiTrendPoint] = []


class KpiRadarResponse(BaseModel):
    overall_achievement: float
    dimensions: List[RadarDimension]
    by_kind: List[KpiKindSummary] = []
    series: List[KpiTrendSeries] = []


class ImprovementCandidateOut(BaseModel):
    """红/黄 KPI 中尚未有进行中改善项目的候选。"""

    kpi_id: int
    code: str
    name: str
    status: str
    status_label: str
    latest_value: Optional[float] = None
    target_value: Optional[float] = None
    unit: Optional[str] = None
    red_threshold: Optional[float] = None
    yellow_threshold: Optional[float] = None
    green_threshold: Optional[float] = None
    process_id: Optional[int] = None
    process_code: Optional[str] = None
    process_name: Optional[str] = None
    owner: Optional[str] = None
    owner_user_id: Optional[int] = None


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
