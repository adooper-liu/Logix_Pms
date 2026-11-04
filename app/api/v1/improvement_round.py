"""薄轮次原引用及快照接口，不提供advance或新阶段。"""

from typing import Optional

from fastapi import APIRouter, Header

from app.api.deps import CurrentUser, DbSession, WriteUser
from app.schemas.improvement_round import (
    AcceptanceIn,
    AfterIn,
    BindIn,
    RevisionIn,
    RoundDraft,
    RoundOut,
    RoundPatch,
)
from app.services import improvement_round as service

router = APIRouter(prefix="/processes/{process_id}/improvement-rounds", tags=["薄轮次对照"])


@router.get("", response_model=list[RoundOut])
def list_rounds(process_id: int, db: DbSession, user: CurrentUser):
    return service.list_rounds(db, user, process_id)


@router.post("", response_model=RoundOut, status_code=201)
def create_round(
    process_id: int,
    payload: RoundDraft,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, None, "create", payload, key)


@router.get("/{round_id}", response_model=RoundOut)
def get_round(process_id: int, round_id: int, db: DbSession, user: CurrentUser):
    return service.out(service.require(db, user, process_id, round_id))


@router.patch("/{round_id}", response_model=RoundOut)
def patch_round(
    process_id: int,
    round_id: int,
    payload: RoundPatch,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "patch", payload, key)


@router.post("/{round_id}/lock-baseline", response_model=RoundOut)
def lock_baseline(
    process_id: int,
    round_id: int,
    payload: RevisionIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "lock-baseline", payload, key)


@router.post("/{round_id}/revise", response_model=RoundOut, status_code=201)
def revise(
    process_id: int,
    round_id: int,
    payload: RevisionIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "revise", payload, key)


@router.post("/{round_id}/bind-project", response_model=RoundOut)
def bind_project(
    process_id: int,
    round_id: int,
    payload: BindIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "bind-project", payload, key)


@router.post("/{round_id}/bind-design", response_model=RoundOut)
def bind_design(
    process_id: int,
    round_id: int,
    payload: BindIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "bind-design", payload, key)


@router.post("/{round_id}/bind-published", response_model=RoundOut)
def bind_published(
    process_id: int,
    round_id: int,
    payload: BindIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "bind-published", payload, key)


@router.post("/{round_id}/lock-acceptance", response_model=RoundOut)
def lock_acceptance(
    process_id: int,
    round_id: int,
    payload: AcceptanceIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "lock-acceptance", payload, key)


@router.post("/{round_id}/capture-after", response_model=RoundOut)
def capture_after(
    process_id: int,
    round_id: int,
    payload: AfterIn,
    db: DbSession,
    user: WriteUser,
    key: Optional[str] = Header(None, alias="Idempotency-Key"),
):
    return service.execute(db, user, process_id, round_id, "capture-after", payload, key)
