"""流程卡 API。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.schemas.process_card import ProcessCardOut
from app.services import process_card as card_service

router = APIRouter(prefix="/process-card", tags=["流程卡"])


@router.get("/{process_id}", response_model=ProcessCardOut, summary="流程卡：跨模块聚合视图")
def process_card(process_id: int, db: DbSession, user: CurrentUser):
    try:
        return card_service.build(db, process_id)
    except card_service.ProcessCardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
