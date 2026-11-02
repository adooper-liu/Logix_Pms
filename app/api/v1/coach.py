"""实训指导接口。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.coach import CoachOut
from app.services import coach as coach_service

router = APIRouter(prefix="/train", tags=["实训"])


@router.get("/coach", response_model=CoachOut, summary="按模块给出下一步")
def coach(
    db: DbSession,
    user: CurrentUser,
    area: str = Query(default="bpm"),
):
    return coach_service.advise(db, area)
