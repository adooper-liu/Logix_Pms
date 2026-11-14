"""Read-only process operating summary endpoint."""

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession
from app.schemas.process_operating import ProcessOperatingSummaryOut
from app.services.process_operating_summary import sample_operating_summary

router = APIRouter(prefix="/processes", tags=["流程经营"])


@router.get(
    "/{process_id}/operating-summary",
    response_model=ProcessOperatingSummaryOut,
    summary="读取流程经营摘要",
)
def operating_summary(process_id: int, db: DbSession, user: CurrentUser):
    try:
        return sample_operating_summary(db, process_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
