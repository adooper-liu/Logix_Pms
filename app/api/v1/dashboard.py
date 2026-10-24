"""管理驾驶舱。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.dashboard import DashboardHome, DashboardOverview
from app.services import dashboard as dashboard_service

router = APIRouter(prefix="/dashboard", tags=["管理驾驶舱"])


@router.get(
    "/overview", response_model=DashboardOverview, summary="驾驶舱总览（一次拉齐首页所需数据）"
)
def overview(db: DbSession, board_limit: int = Query(default=8, ge=1, le=30)):
    return dashboard_service.build_overview(db, board_limit=board_limit)


@router.get(
    "/home", response_model=DashboardHome, summary="角色化工作台（按当前用户角色返回待办与入口）"
)
def home(db: DbSession, user: CurrentUser):
    return dashboard_service.build_home(db, user)
