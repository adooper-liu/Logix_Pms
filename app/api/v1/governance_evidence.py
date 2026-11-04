"""原控制复盘及只读保障来源，不生成平行任务。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, WriteUser
from app.services import governance_evidence as service
from app.services.adoption_review import ReviewIn
from app.services.governance_evidence import ControlIn

router = APIRouter(prefix="/processes/{process_id}", tags=["持续治理"])


@router.get("/governance-evidence")
def evidence(process_id: int, db: DbSession, user: CurrentUser):
    return service.evidence(db, user, process_id)


@router.post("/control-reviews", status_code=201)
def create(process_id: int, payload: ControlIn, db: DbSession, user: WriteUser):
    return service.create(db, user, process_id, payload)


@router.post("/control-reviews/{record_id}/review")
def review(process_id: int, record_id: int, payload: ReviewIn, db: DbSession, user: WriteUser):
    return service.review(db, user, process_id, record_id, payload)
