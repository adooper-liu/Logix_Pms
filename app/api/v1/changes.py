"""变更申请 API：草稿、审批、取消与发布门禁证据。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.enums import ChangeStatus
from app.schemas.change import (
    ChangeDecisionRequest,
    ChangeMetaOut,
    ChangeRequestCreate,
    ChangeRequestOut,
    ChangeRequestUpdate,
)
from app.schemas.common import as_columns
from app.services import audit as audit_service
from app.services import change as change_service

router = APIRouter(prefix="/changes", tags=["变更治理"])


def _require(db: DbSession, change_id: int):
    try:
        return change_service.require_change(db, change_id)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/meta", response_model=ChangeMetaOut, summary="变更单枚举中文标签")
def change_meta():
    return ChangeMetaOut(
        change_type_labels=change_service.CHANGE_TYPE_LABELS,
        impact_level_labels=change_service.IMPACT_LEVEL_LABELS,
        status_labels=change_service.STATUS_LABELS,
        impact_keys=list(change_service.IMPACT_KEYS),
        impact_labels=change_service.IMPACT_LABELS,
    )


@router.get("", response_model=List[ChangeRequestOut], summary="变更申请清单")
def list_changes(
    db: DbSession,
    user: CurrentUser,
    process_id: Optional[int] = None,
    status_: Optional[ChangeStatus] = Query(default=None, alias="status"),
    year: Optional[int] = None,
):
    return change_service.list_changes(
        db,
        process_id=process_id,
        status=status_.value if status_ else None,
        year=year,
    )


@router.get("/{change_id}", response_model=ChangeRequestOut, summary="变更申请详情")
def get_change(change_id: int, db: DbSession, user: CurrentUser):
    return change_service.change_out(db, _require(db, change_id))


@router.post(
    "",
    response_model=ChangeRequestOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建变更申请（草稿）",
)
def create_change(payload: ChangeRequestCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump())
    data["impact"] = payload.impact.model_dump()
    try:
        row = change_service.create_change(db, data, user)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_change_request",
        row.id,
        f"新建变更申请 {row.code}：{row.title}",
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)


@router.patch("/{change_id}", response_model=ChangeRequestOut, summary="修改变更申请（仅草稿）")
def update_change(
    change_id: int,
    payload: ChangeRequestUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = _require(db, change_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    if "impact" in data and data["impact"] is not None:
        data["impact"] = payload.impact.model_dump()
    try:
        change_service.update_change(db, row, data)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_change_request",
        row.id,
        f"修改变更申请 {row.code}（{', '.join(sorted(data))}）",
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)


@router.post("/{change_id}/submit", response_model=ChangeRequestOut, summary="提交审批")
def submit_change(change_id: int, db: DbSession, user: ManagerUser):
    row = _require(db, change_id)
    try:
        change_service.submit_change(db, row)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "UPDATE", "process_change_request", row.id, f"提交变更申请 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)


@router.post("/{change_id}/approve", response_model=ChangeRequestOut, summary="批准变更")
def approve_change(
    change_id: int,
    payload: ChangeDecisionRequest,
    db: DbSession,
    user: ManagerUser,
):
    row = _require(db, change_id)
    try:
        change_service.approve_change(db, row, user, payload.note)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "UPDATE", "process_change_request", row.id, f"批准变更申请 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)


@router.post("/{change_id}/reject", response_model=ChangeRequestOut, summary="驳回变更")
def reject_change(
    change_id: int,
    payload: ChangeDecisionRequest,
    db: DbSession,
    user: ManagerUser,
):
    row = _require(db, change_id)
    try:
        change_service.reject_change(db, row, user, payload.note)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "UPDATE", "process_change_request", row.id, f"驳回变更申请 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)


@router.post("/{change_id}/cancel", response_model=ChangeRequestOut, summary="取消变更")
def cancel_change(change_id: int, db: DbSession, user: ManagerUser):
    row = _require(db, change_id)
    try:
        change_service.cancel_change(db, row)
    except change_service.ChangeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.record(
        db, user, "UPDATE", "process_change_request", row.id, f"取消变更申请 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return change_service.change_out(db, row)
