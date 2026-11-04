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
        result = card_service.build(db, process_id)
        from app.schemas.process_card import CardSheetOut
        from app.services.handoff import for_process, require_sheet
        from app.services.tool_sheet import sheets_for_process

        result.handoffs = for_process(db, user, process_id)
        visible = []
        for item in sheets_for_process(db, process_id):
            try:
                require_sheet(db, user, item["tool_code"], item["id"])
                visible.append(CardSheetOut(**item))
            except HTTPException as exc:
                if exc.status_code != 404:
                    raise
        result.sheets = visible
        return result
    except card_service.ProcessCardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
