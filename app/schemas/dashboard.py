"""管理驾驶舱出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class KpiCard(BaseModel):
    key: str
    label: str
    value: float
    unit: Optional[str] = None
    delta: Optional[float] = Field(default=None, description="环比变化")
    trend: Optional[str] = Field(default=None, description="UP / DOWN / FLAT")
    status: str = Field(default="NORMAL", description="NORMAL / WATCH / RISK")


class StageHealth(BaseModel):
    stage_no: int
    stage_name: str
    project_count: int
    avg_progress: float
    done_steps: int
    total_steps: int
    health: str = Field(description="GOOD / WATCH / RISK")


class MethodologySlice(BaseModel):
    methodology: str
    label: str
    count: int
    share: float


class ProjectBoardItem(BaseModel):
    id: int
    code: str
    name: str
    methodology: str
    methodology_label: Optional[str] = None
    status: str
    status_label: Optional[str] = None
    current_stage: int
    stage_name: str
    priority: int
    owner: str
    progress: float
    improvement_pct: Optional[float] = None
    metric_name: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    metric_unit: Optional[str] = None
    is_overdue: bool = False


class HealthAlert(BaseModel):
    process_id: int
    code: str
    name: str
    health_score: Optional[float] = None
    pain_score: float
    priority_score: float
    reason: str
    level: str


class DashboardOverview(BaseModel):
    cards: List[KpiCard]
    stage_health: List[StageHealth]
    methodology_distribution: List[MethodologySlice]
    project_board: List[ProjectBoardItem]
    health_alerts: List[HealthAlert]
    exception_summary: dict
    knowledge_count: int
