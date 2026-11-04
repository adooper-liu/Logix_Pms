"""开始使用 API：流程框架边界，以及单条流程的范围说明。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.startup import (
    CharterContextOut,
    CharterIn,
    CharterOptionsOut,
    CharterUpdate,
    StartupPilotConfirmIn,
    StartupSkipIn,
    StartupStatusOut,
)
from app.services import charter as charter_service
from app.services import startup as startup_service

router = APIRouter(prefix="/start", tags=["启动向导"])


@router.get(
    "/status", response_model=StartupStatusOut, summary="流程框架边界（按现有数据自动计算）"
)
def startup_status(db: DbSession, user: CurrentUser):
    return startup_service.status(db)


@router.post(
    "/steps/{step_key}/skip",
    response_model=StartupStatusOut,
    summary="跳过启动步骤（标记未验证，MANAGER+）",
)
def skip_step(step_key: str, payload: StartupSkipIn, db: DbSession, user: ManagerUser):
    try:
        return startup_service.skip_step(db, step_key, payload.reason, user)
    except startup_service.StartupStepNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/steps/{step_key}/skip",
    response_model=StartupStatusOut,
    summary="取消跳过启动步骤（MANAGER+）",
)
def unskip_step(step_key: str, db: DbSession, user: ManagerUser):
    try:
        return startup_service.unskip_step(db, step_key, user)
    except startup_service.StartupStepNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/pilot/confirm",
    response_model=StartupStatusOut,
    summary="确认首次上线（S0–S7 全部就绪才允许，MANAGER+）",
)
def confirm_pilot(payload: StartupPilotConfirmIn, db: DbSession, user: ManagerUser):
    try:
        return startup_service.confirm_pilot(db, user, payload.note)
    except startup_service.PilotGateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete(
    "/pilot/confirm",
    response_model=StartupStatusOut,
    summary="撤销首次上线确认（MANAGER+）",
)
def revoke_pilot(db: DbSession, user: ManagerUser):
    return startup_service.revoke_pilot(db, user)


@router.get(
    "/charter-options",
    response_model=CharterOptionsOut,
    summary="范围说明表单的可选项",
)
def charter_options(db: DbSession, user: CurrentUser):
    return startup_service.charter_options(db)


@router.get(
    "/charters/{process_id}", response_model=CharterContextOut, summary="流程范围、客户结果及原依据"
)
def get_charter(process_id: int, db: DbSession, user: CurrentUser):
    return charter_service.context(db, process_id, user)


@router.put(
    "/charters/{process_id}", response_model=CharterContextOut, summary="修订原流程章程（MANAGER+）"
)
def update_charter(process_id: int, payload: CharterUpdate, db: DbSession, user: ManagerUser):
    if process_id != payload.process_id:
        raise HTTPException(400, "流程身份不一致")
    return charter_service.save(db, user, payload)


@router.post(
    "/charters",
    response_model=StartupStatusOut,
    summary="写入一条 L3 的范围说明（MANAGER+）",
)
def save_charter(payload: CharterIn, db: DbSession, user: ManagerUser):
    try:
        return startup_service.save_charter(db, user, payload)
    except startup_service.CharterError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
