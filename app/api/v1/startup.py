"""启动向导 API：九步 readiness 与下一步动作。"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.startup import StartupStatusOut
from app.services import startup as startup_service

router = APIRouter(prefix="/start", tags=["启动向导"])


@router.get(
    "/status", response_model=StartupStatusOut, summary="九步启动状态（按现有数据自动计算）"
)
def startup_status(db: DbSession, user: CurrentUser):
    return startup_service.status(db)
