"""十层单页 API：试点路径、层状态、待办与异常改善卡。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser, resolve_owner
from app.schemas.common import DeleteResult, as_columns
from app.schemas.pilot import (
    PilotIssueCreate,
    PilotIssueOut,
    PilotIssueUpdate,
    PilotLayerUpdate,
    PilotMetaOut,
    PilotPathCreate,
    PilotPathOut,
    PilotPathSummaryOut,
    PilotPathUpdate,
    PilotTaskCreate,
    PilotTaskOut,
    PilotTaskUpdate,
)
from app.services import audit as audit_service
from app.services import pilot as pilot_service

router = APIRouter(prefix="/pilot", tags=["十层单页"])


def _error(exc: pilot_service.PilotError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _gate(exc: pilot_service.PilotGateError) -> None:
    raise HTTPException(
        status_code=409,
        detail={"message": str(exc), "missing": exc.missing},
    ) from exc


@router.get("/meta", response_model=PilotMetaOut, summary="十层单页中文标签")
def pilot_meta():
    return PilotMetaOut(
        path_status_labels=pilot_service.PATH_STATUS_LABELS,
        layer_status_labels=pilot_service.LAYER_STATUS_LABELS,
        task_status_labels=pilot_service.TASK_STATUS_LABELS,
        issue_status_labels=pilot_service.ISSUE_STATUS_LABELS,
        priority_labels=pilot_service.PRIORITY_LABELS,
        severity_labels=pilot_service.SEVERITY_LABELS,
    )


@router.get("/paths", response_model=List[PilotPathSummaryOut], summary="试点路径清单")
def list_paths(db: DbSession, user: CurrentUser):
    return pilot_service.list_paths(db)


@router.post(
    "/paths",
    response_model=PilotPathOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建试点路径（MANAGER+）",
)
def create_path(payload: PilotPathCreate, db: DbSession, user: ManagerUser):
    owner_user_id, owner = resolve_owner(db, payload.owner_user_id, payload.owner)
    if owner_user_id is None:
        owner_user_id, owner = user.id, user.display_name
    try:
        detail = pilot_service.create_path(
            db, payload.name, payload.process_id, owner_user_id, owner
        )
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(db, user, "CREATE", "pilot_path", detail.id, f"新建试点路径 {detail.name}")
    db.commit()
    return detail


@router.get("/paths/{path_id}", response_model=PilotPathOut, summary="试点路径详情（十层）")
def get_path(path_id: int, db: DbSession, user: CurrentUser):
    try:
        path = pilot_service.require_path(db, path_id)
    except pilot_service.PilotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return pilot_service.path_detail(db, path)


@router.patch("/paths/{path_id}", response_model=PilotPathOut, summary="更新试点路径（MANAGER+）")
def update_path(path_id: int, payload: PilotPathUpdate, db: DbSession, user: ManagerUser):
    try:
        path = pilot_service.require_path(db, path_id)
        data = payload.model_dump(exclude_unset=True)
        if "owner_user_id" in data or "owner" in data:
            owner_user_id, owner = resolve_owner(db, data.get("owner_user_id"), data.get("owner"))
        else:
            owner_user_id, owner = None, None
        detail = pilot_service.update_path(
            db,
            path,
            data.get("name"),
            as_columns({"status": data.get("status")}).get("status"),
            owner_user_id,
            owner,
        )
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(db, user, "UPDATE", "pilot_path", detail.id, f"更新试点路径 {detail.name}")
    db.commit()
    return detail


@router.delete("/paths/{path_id}", response_model=DeleteResult, summary="删除试点路径（MANAGER+）")
def delete_path(path_id: int, db: DbSession, user: ManagerUser):
    try:
        path = pilot_service.require_path(db, path_id)
    except pilot_service.PilotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    name = path.name
    pilot_service.delete_path(db, path)
    audit_service.record(db, user, "DELETE", "pilot_path", path_id, f"删除试点路径 {name}")
    db.commit()
    return DeleteResult(deleted=1)


@router.post(
    "/paths/{path_id}/advance",
    response_model=PilotPathOut,
    summary="进入下一层（当前层退出门必须满足）",
)
def advance_path(path_id: int, db: DbSession, user: ManagerUser):
    try:
        path = pilot_service.require_path(db, path_id)
        detail = pilot_service.advance_path(db, path)
    except pilot_service.PilotGateError as exc:
        _gate(exc)
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(
        db, user, "UPDATE", "pilot_path", detail.id, f"推进试点路径到第 {detail.current_layer} 层"
    )
    db.commit()
    return detail


@router.patch(
    "/paths/{path_id}/layers/{layer_no}",
    response_model=PilotPathOut,
    summary="保存层备注 / 上下文摘要（WRITE 角色）",
)
def update_layer(
    path_id: int,
    layer_no: int,
    payload: PilotLayerUpdate,
    db: DbSession,
    user: WriteUser,
):
    try:
        path = pilot_service.require_path(db, path_id)
        detail = pilot_service.update_layer(
            db, path, layer_no, payload.context_summary, payload.notes
        )
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(db, user, "UPDATE", "pilot_layer", path_id, f"更新第 {layer_no} 层备注")
    db.commit()
    return detail


@router.post(
    "/paths/{path_id}/tasks",
    response_model=PilotTaskOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增层内待办（WRITE 角色）",
)
def create_task(path_id: int, payload: PilotTaskCreate, db: DbSession, user: WriteUser):
    try:
        path = pilot_service.require_path(db, path_id)
        owner_user_id, owner = resolve_owner(db, payload.owner_user_id, payload.owner)
        task = pilot_service.create_task(
            db,
            path,
            payload.layer_no,
            payload.title,
            as_columns({"priority": payload.priority}).get("priority"),
            owner_user_id,
            owner,
            payload.due_date,
            payload.acceptance,
        )
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(db, user, "CREATE", "pilot_task", task.id, f"新增待办 {task.title}")
    db.commit()
    return task


@router.patch("/tasks/{task_id}", response_model=PilotTaskOut, summary="更新待办（WRITE 角色）")
def update_task(task_id: int, payload: PilotTaskUpdate, db: DbSession, user: WriteUser):
    try:
        task = pilot_service.require_task(db, task_id)
        data = as_columns(payload.model_dump(exclude_unset=True))
        if "owner_user_id" in data or "owner" in data:
            owner_user_id, owner = resolve_owner(db, data.get("owner_user_id"), data.get("owner"))
            data["owner_user_id"] = owner_user_id
            data["owner"] = owner
        task = pilot_service.update_task(db, task, data)
    except pilot_service.PilotError as exc:
        _error(exc)
    db.commit()
    return task


@router.delete("/tasks/{task_id}", response_model=DeleteResult, summary="删除待办（WRITE 角色）")
def delete_task(task_id: int, db: DbSession, user: WriteUser):
    try:
        task = pilot_service.require_task(db, task_id)
    except pilot_service.PilotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pilot_service.delete_task(db, task)
    db.commit()
    return DeleteResult(deleted=1)


@router.post(
    "/paths/{path_id}/issues",
    response_model=PilotIssueOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增异常/改善卡（WRITE 角色）",
)
def create_issue(path_id: int, payload: PilotIssueCreate, db: DbSession, user: WriteUser):
    try:
        path = pilot_service.require_path(db, path_id)
        owner_user_id, owner = resolve_owner(db, payload.owner_user_id, payload.owner)
        issue = pilot_service.create_issue(
            db,
            path,
            payload.layer_no,
            payload.title,
            as_columns({"severity": payload.severity}).get("severity"),
            payload.workaround,
            payload.verification,
            owner_user_id,
            owner,
            payload.due_date,
        )
    except pilot_service.PilotError as exc:
        _error(exc)
    audit_service.record(db, user, "CREATE", "pilot_issue", issue.id, f"新增异常 {issue.title}")
    db.commit()
    return issue


@router.patch("/issues/{issue_id}", response_model=PilotIssueOut, summary="更新异常（WRITE 角色）")
def update_issue(issue_id: int, payload: PilotIssueUpdate, db: DbSession, user: WriteUser):
    try:
        issue = pilot_service.require_issue(db, issue_id)
        data = as_columns(payload.model_dump(exclude_unset=True))
        if "owner_user_id" in data or "owner" in data:
            owner_user_id, owner = resolve_owner(db, data.get("owner_user_id"), data.get("owner"))
            data["owner_user_id"] = owner_user_id
            data["owner"] = owner
        issue = pilot_service.update_issue(db, issue, data)
    except pilot_service.PilotError as exc:
        _error(exc)
    db.commit()
    return issue


@router.delete("/issues/{issue_id}", response_model=DeleteResult, summary="删除异常（WRITE 角色）")
def delete_issue(issue_id: int, db: DbSession, user: WriteUser):
    try:
        issue = pilot_service.require_issue(db, issue_id)
    except pilot_service.PilotError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    pilot_service.delete_issue(db, issue)
    db.commit()
    return DeleteResult(deleted=1)
