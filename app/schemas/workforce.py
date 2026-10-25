"""工作量预测与派工均衡出入参。"""

from __future__ import annotations

from datetime import date
from typing import List, Optional

from pydantic import BaseModel


class WorkloadForecastRowOut(BaseModel):
    period: date
    org_unit_id: Optional[int] = None
    org_unit_name: Optional[str] = None
    position_id: int
    position_name: Optional[str] = None
    demand_minutes: float = 0
    available_minutes: float = 0
    gap_minutes: float = 0
    utilization: Optional[float] = None


class WorkloadForecastOut(BaseModel):
    base_period: date
    months: int
    growth_pct: float
    rows: List[WorkloadForecastRowOut] = []
    total_demand_minutes: float = 0
    total_available_minutes: float = 0
    total_gap_minutes: float = 0


class BalanceSuggestionOut(BaseModel):
    from_org_unit_id: Optional[int] = None
    from_org_unit_name: Optional[str] = None
    from_position_id: int
    from_position_name: Optional[str] = None
    to_org_unit_id: Optional[int] = None
    to_org_unit_name: Optional[str] = None
    to_position_id: int
    to_position_name: Optional[str] = None
    hours: float


class BalanceOut(BaseModel):
    period: date
    deficit_positions: int = 0
    spare_positions: int = 0
    suggestions: List[BalanceSuggestionOut] = []
    total_gap_minutes: float = 0
