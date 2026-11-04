"""只读生命周期任务目录，不创建业务状态。"""

from typing import Optional

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.schemas.lifecycle import LifecycleOut
from app.services.lifecycle import catalog

router = APIRouter(prefix="/lifecycle", tags=["生命周期任务"])


@router.get("", response_model=LifecycleOut, summary="八阶段任务、原产物与上下文")
def lifecycle_catalog(
    db: DbSession,
    user: CurrentUser,
    process_id: Optional[int] = Query(None, ge=1),
    project_id: Optional[int] = Query(None, ge=1),
):
    return catalog(db, user, process_id, project_id)
