"""原建模、分析、设计作业入口，不增加项目阶段。"""

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession, WriteUser
from app.schemas.tool_sheet import ToolSheetOut
from app.schemas.workbench import WorkbenchOut, WorkRecordIn, WorkReviewIn
from app.services import workbench

router = APIRouter(tags=["流程作业"])


@router.get("/processes/{process_id}/workbench", response_model=WorkbenchOut)
def get_workbench(process_id: int, db: DbSession, user: CurrentUser):
    return workbench.board(db, user, process_id)


@router.post("/processes/{process_id}/work-records", response_model=ToolSheetOut, status_code=201)
def create_work(process_id: int, payload: WorkRecordIn, db: DbSession, user: WriteUser):
    return workbench.create(db, user, process_id, payload)


@router.post("/processes/{process_id}/work-records/{sheet_id}/review", response_model=ToolSheetOut)
def review_work(
    process_id: int, sheet_id: int, payload: WorkReviewIn, db: DbSession, user: WriteUser
):
    return workbench.review(db, user, process_id, sheet_id, payload)
