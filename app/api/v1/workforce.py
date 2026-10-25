"""工作量预测与派工均衡 API。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.workforce import BalanceOut, WorkloadForecastOut
from app.services import workforce as workforce_service

router = APIRouter(prefix="/workforce", tags=["工作量预测"])


@router.get(
    "/forecast",
    response_model=WorkloadForecastOut,
    summary="按已验证标准工时预测未来数月的需求与缺口",
)
def forecast(
    db: DbSession,
    user: CurrentUser,
    months: int = Query(default=3, ge=1, le=12),
    growth_pct: float = Query(default=0, ge=-50, le=100),
):
    return workforce_service.forecast(db, months=months, growth_pct=growth_pct)


@router.get(
    "/balance",
    response_model=BalanceOut,
    summary="派工均衡建议（Manager）",
)
def balance(db: DbSession, user: ManagerUser):
    return workforce_service.balancing(db)
