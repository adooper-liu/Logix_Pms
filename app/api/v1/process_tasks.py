"""L5 任务目录 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, ManagerUser, WriteUser
from app.schemas.process_task import (
    ProcessTaskCreate,
    ProcessTaskOut,
    ProcessTaskRollupOut,
    ProcessTaskUpdate,
)
from app.services import audit as audit_service
from app.services import process_task as task_service

router = APIRouter(prefix="/process-tasks", tags=["L5 任务目录"])


def _fail(exc: task_service.ProcessTaskError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[ProcessTaskOut], summary="L5 任务清单")
def list_tasks(
    db: DbSession,
    activity_id: Optional[int] = None,
    process_id: Optional[int] = None,
    include_inactive: bool = False,
    limit: int = Query(default=500, ge=1, le=1000),
):
    return [
        task_service.task_out(row)
        for row in task_service.list_tasks(
            db,
            activity_id=activity_id,
            process_id=process_id,
            include_inactive=include_inactive,
            limit=limit,
        )
    ]


@router.get(
    "/rollup",
    response_model=ProcessTaskRollupOut,
    summary="按 L4 活动汇总 L5 任务与标准工时",
)
def task_rollup(db: DbSession, activity_id: int = Query(ge=1)):
    try:
        return task_service.rollup(db, activity_id)
    except task_service.ProcessTaskError as exc:
        _fail(exc)


@router.post(
    "",
    response_model=ProcessTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增 L5 任务",
)
def create_task(payload: ProcessTaskCreate, db: DbSession, user: WriteUser):
    try:
        row = task_service.create_task(db, payload.model_dump())
    except task_service.ProcessTaskError as exc:
        _fail(exc)
    audit_service.record(
        db, user, "CREATE", "process_task", row.id, f"新增 L5 任务 {row.code} {row.name}"
    )
    db.commit()
    db.refresh(row)
    return task_service.task_out(row)


@router.patch("/{task_id}", response_model=ProcessTaskOut, summary="修改 L5 任务")
def update_task(task_id: int, payload: ProcessTaskUpdate, db: DbSession, user: WriteUser):
    row = db.get(task_service.ProcessTaskDefinition, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="L5 任务不存在")
    try:
        task_service.update_task(db, row, payload.model_dump(exclude_unset=True))
    except task_service.ProcessTaskError as exc:
        _fail(exc)
    audit_service.record(db, user, "UPDATE", "process_task", row.id, f"修改 L5 任务 {row.code}")
    db.commit()
    db.refresh(row)
    return task_service.task_out(row)


@router.delete("/{task_id}", summary="停用 L5 任务")
def deactivate_task(task_id: int, db: DbSession, user: ManagerUser):
    row = db.get(task_service.ProcessTaskDefinition, task_id)
    if row is None:
        raise HTTPException(status_code=404, detail="L5 任务不存在")
    row.is_active = False
    audit_service.record(db, user, "UPDATE", "process_task", row.id, f"停用 L5 任务 {row.code}")
    db.commit()
    return {"deleted": 1}
