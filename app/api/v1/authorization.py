"""分级授权矩阵 API：A/B/C/D 规则与例外台账。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.schemas.authorization import (
    AuthorizationDecisionIn,
    AuthorizationExceptionCreate,
    AuthorizationExceptionOut,
    AuthorizationMetaOut,
    AuthorizationRuleCreate,
    AuthorizationRuleOut,
    AuthorizationRuleUpdate,
)
from app.schemas.common import DeleteResult
from app.services import audit as audit_service
from app.services import authorization as authz_service

router = APIRouter(prefix="/authorization", tags=["分级授权"])


def _raise(exc: authz_service.AuthorizationError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/meta", response_model=AuthorizationMetaOut, summary="授权类别与状态中文标签")
def authorization_meta():
    return AuthorizationMetaOut(
        category_labels=authz_service.CATEGORY_LABELS,
        status_labels=authz_service.STATUS_LABELS,
        exception_status_labels=authz_service.EXCEPTION_STATUS_LABELS,
        risk_labels=authz_service.RISK_LABELS,
    )


@router.get("/rules", response_model=List[AuthorizationRuleOut], summary="授权规则清单")
def list_rules(
    db: DbSession,
    user: CurrentUser,
    process_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
    category: Optional[str] = Query(default=None, pattern="^[ABCD]$"),
    status_: Optional[str] = Query(default=None, alias="status"),
    keyword: Optional[str] = None,
):
    rows = authz_service.list_rules(
        db,
        process_id=process_id,
        org_unit_id=org_unit_id,
        category=category,
        status=status_,
        keyword=keyword,
    )
    return [authz_service.rule_out(db, row) for row in rows]


@router.get("/rules/{rule_id}", response_model=AuthorizationRuleOut, summary="授权规则详情")
def get_rule(rule_id: int, db: DbSession, user: CurrentUser):
    try:
        row = authz_service.require_rule(db, rule_id)
    except authz_service.AuthorizationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return authz_service.rule_out(db, row)


@router.post(
    "/rules",
    response_model=AuthorizationRuleOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建授权规则（MANAGER+）",
)
def create_rule(payload: AuthorizationRuleCreate, db: DbSession, user: ManagerUser):
    try:
        row = authz_service.create_rule(db, payload, user)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "CREATE", "authorization_rule", row.id, f"新建授权规则 {row.code} {row.title}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.rule_out(db, row)


@router.patch(
    "/rules/{rule_id}", response_model=AuthorizationRuleOut, summary="修改授权规则（MANAGER+）"
)
def update_rule(rule_id: int, payload: AuthorizationRuleUpdate, db: DbSession, user: ManagerUser):
    try:
        row = authz_service.require_rule(db, rule_id)
        authz_service.update_rule(db, row, payload)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_rule", row.id, f"修改授权规则 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.rule_out(db, row)


@router.post(
    "/rules/{rule_id}/activate",
    response_model=AuthorizationRuleOut,
    summary="生效授权规则（MANAGER+）",
)
def activate_rule(rule_id: int, db: DbSession, user: ManagerUser):
    try:
        row = authz_service.require_rule(db, rule_id)
        authz_service.activate_rule(db, row)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_rule", row.id, f"生效授权规则 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.rule_out(db, row)


@router.post(
    "/rules/{rule_id}/retire",
    response_model=AuthorizationRuleOut,
    summary="停用授权规则（MANAGER+）",
)
def retire_rule(rule_id: int, db: DbSession, user: ManagerUser):
    try:
        row = authz_service.require_rule(db, rule_id)
        authz_service.retire_rule(db, row)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_rule", row.id, f"停用授权规则 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.rule_out(db, row)


@router.delete("/rules/{rule_id}", response_model=DeleteResult, summary="删除草稿规则（MANAGER+）")
def delete_rule(rule_id: int, db: DbSession, user: ManagerUser):
    try:
        row = authz_service.require_rule(db, rule_id)
        code = row.code
        authz_service.delete_rule(db, row)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(db, user, "DELETE", "authorization_rule", rule_id, f"删除授权规则 {code}")
    db.commit()
    return DeleteResult(deleted=1)


@router.get("/exceptions", response_model=List[AuthorizationExceptionOut], summary="例外台账")
def list_exceptions(
    db: DbSession,
    user: CurrentUser,
    rule_id: Optional[int] = None,
    process_id: Optional[int] = None,
    status_: Optional[str] = Query(default=None, alias="status"),
):
    rows = authz_service.list_exceptions(db, rule_id=rule_id, process_id=process_id, status=status_)
    return [authz_service.exception_out(db, row) for row in rows]


@router.post(
    "/exceptions",
    response_model=AuthorizationExceptionOut,
    status_code=status.HTTP_201_CREATED,
    summary="申请例外（WRITE 角色）",
)
def create_exception(payload: AuthorizationExceptionCreate, db: DbSession, user: WriteUser):
    try:
        row = authz_service.create_exception(db, payload, user)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "CREATE", "authorization_exception", row.id, f"申请授权例外 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.exception_out(db, row)


@router.post(
    "/exceptions/{exception_id}/approve",
    response_model=AuthorizationExceptionOut,
    summary="批准例外（MANAGER+）",
)
def approve_exception(
    exception_id: int, payload: AuthorizationDecisionIn, db: DbSession, user: ManagerUser
):
    try:
        row = authz_service.require_exception(db, exception_id)
        authz_service.decide_exception(db, row, user, True, payload.note)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_exception", row.id, f"批准例外 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.exception_out(db, row)


@router.post(
    "/exceptions/{exception_id}/reject",
    response_model=AuthorizationExceptionOut,
    summary="驳回例外（MANAGER+）",
)
def reject_exception(
    exception_id: int, payload: AuthorizationDecisionIn, db: DbSession, user: ManagerUser
):
    try:
        row = authz_service.require_exception(db, exception_id)
        authz_service.decide_exception(db, row, user, False, payload.note)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_exception", row.id, f"驳回例外 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.exception_out(db, row)


@router.post(
    "/exceptions/{exception_id}/close",
    response_model=AuthorizationExceptionOut,
    summary="关闭已批准的例外（MANAGER+）",
)
def close_exception(
    exception_id: int, payload: AuthorizationDecisionIn, db: DbSession, user: ManagerUser
):
    try:
        row = authz_service.require_exception(db, exception_id)
        authz_service.close_exception(db, row, user, payload.note)
    except authz_service.AuthorizationError as exc:
        _raise(exc)
    audit_service.record(
        db, user, "UPDATE", "authorization_exception", row.id, f"关闭例外 {row.code}"
    )
    db.commit()
    db.refresh(row)
    return authz_service.exception_out(db, row)
