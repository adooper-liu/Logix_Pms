"""工作量预测与派工均衡。

预测只使用已验证标准工时和已登记产能，不做无依据的需求放大；
均衡建议只给「把多少小时从哪个岗位转到哪个岗位」，不自动改派。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List

from sqlalchemy.orm import Session

from app.schemas.workforce import (
    BalanceOut,
    BalanceSuggestionOut,
    WorkloadForecastOut,
    WorkloadForecastRowOut,
)
from app.services import workload as workload_service


def _add_months(period: date, months: int) -> date:
    month = period.month - 1 + months
    year = period.year + month // 12
    month = month % 12 + 1
    day = min(period.day, 28)
    return date(year, month, day)


def forecast(db: Session, months: int = 3, growth_pct: float = 0.0) -> WorkloadForecastOut:
    base = workload_service.summary(db)
    rows: List[WorkloadForecastRowOut] = []
    for index in range(1, months + 1):
        factor = (1 + growth_pct / 100) ** index
        period = _add_months(base.period, index)
        for cap in base.capacity:
            demand = round(cap.demand_minutes * factor, 2)
            available = cap.available_minutes
            gap = round(available - demand, 2)
            rows.append(
                WorkloadForecastRowOut(
                    period=period,
                    org_unit_id=cap.org_unit_id,
                    org_unit_name=cap.org_unit_name,
                    position_id=cap.position_id,
                    position_name=cap.position_name,
                    demand_minutes=demand,
                    available_minutes=available,
                    gap_minutes=gap,
                    utilization=round(demand / available, 4) if available else None,
                )
            )
    total_demand = sum(row.demand_minutes for row in rows)
    total_available = sum(row.available_minutes for row in rows)
    return WorkloadForecastOut(
        base_period=base.period,
        months=months,
        growth_pct=growth_pct,
        rows=rows,
        total_demand_minutes=round(total_demand, 2),
        total_available_minutes=round(total_available, 2),
        total_gap_minutes=round(total_available - total_demand, 2),
    )


def balancing(db: Session) -> BalanceOut:
    base = workload_service.summary(db)
    deficits = [row for row in base.capacity if row.gap_minutes < 0 and row.available_minutes > 0]
    spares = [row for row in base.capacity if row.gap_minutes > 0]
    suggestions: List[BalanceSuggestionOut] = []
    remaining: Dict[int, float] = {row.capacity_id: row.gap_minutes for row in spares}
    for deficit in sorted(deficits, key=lambda row: row.gap_minutes):
        need = -deficit.gap_minutes
        candidates = sorted(
            spares,
            key=lambda row: (
                0 if row.org_unit_id == deficit.org_unit_id else 1,
                -remaining.get(row.capacity_id, 0),
            ),
        )
        for spare in candidates:
            if need <= 0:
                break
            available = remaining.get(spare.capacity_id, 0)
            if available <= 0:
                continue
            moved = round(min(need, available), 2)
            suggestions.append(
                BalanceSuggestionOut(
                    from_org_unit_id=spare.org_unit_id,
                    from_org_unit_name=spare.org_unit_name,
                    from_position_id=spare.position_id,
                    from_position_name=spare.position_name,
                    to_org_unit_id=deficit.org_unit_id,
                    to_org_unit_name=deficit.org_unit_name,
                    to_position_id=deficit.position_id,
                    to_position_name=deficit.position_name,
                    hours=round(moved / 60, 2),
                )
            )
            remaining[spare.capacity_id] = available - moved
            need -= moved
    return BalanceOut(
        period=base.period,
        deficit_positions=len(deficits),
        spare_positions=len(spares),
        suggestions=suggestions,
        total_gap_minutes=round(sum(row.gap_minutes for row in base.capacity), 2),
    )
