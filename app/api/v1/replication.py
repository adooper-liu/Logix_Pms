"""复制资产包 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, WriteUser, ensure_can_edit_owned
from app.schemas.replication import (
    ReplicationPackCreate,
    ReplicationPackOut,
    ReplicationPackUpdate,
)
from app.services import audit as audit_service
from app.services import replication as replication_service

router = APIRouter(prefix="/replication-packs", tags=["复制资产包"])


def _fail(exc: replication_service.ReplicationError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[ReplicationPackOut], summary="复制资产包清单")
def list_packs(
    db: DbSession,
    user: CurrentUser,
    source_project_id: Optional[int] = None,
    status_: Optional[str] = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=500),
):
    return [
        replication_service.pack_out(db, row)
        for row in replication_service.list_packs(
            db, source_project_id=source_project_id, status=status_, limit=limit
        )
    ]


@router.get("/{pack_id}", response_model=ReplicationPackOut, summary="复制资产包详情")
def get_pack(pack_id: int, db: DbSession, user: CurrentUser):
    row = db.get(replication_service.ReplicationPack, pack_id)
    if row is None:
        raise HTTPException(status_code=404, detail="复制资产包不存在")
    return replication_service.pack_out(db, row)


@router.post(
    "",
    response_model=ReplicationPackOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建复制资产包",
)
def create_pack(payload: ReplicationPackCreate, db: DbSession, user: WriteUser):
    try:
        row = replication_service.create_pack(db, payload.model_dump(), user)
    except replication_service.ReplicationError as exc:
        _fail(exc)
    audit_service.record(
        db, user, "CREATE", "replication_pack", row.id, f"新建复制资产包《{row.title}》"
    )
    db.commit()
    db.refresh(row)
    return replication_service.pack_out(db, row)


@router.patch("/{pack_id}", response_model=ReplicationPackOut, summary="修改/发布复制资产包")
def update_pack(pack_id: int, payload: ReplicationPackUpdate, db: DbSession, user: WriteUser):
    row = db.get(replication_service.ReplicationPack, pack_id)
    if row is None:
        raise HTTPException(status_code=404, detail="复制资产包不存在")
    ensure_can_edit_owned(user, row.owner_user_id, row.owner.display_name if row.owner else None)
    try:
        replication_service.update_pack(db, row, payload.model_dump(exclude_unset=True))
    except replication_service.ReplicationError as exc:
        _fail(exc)
    audit_service.record(
        db, user, "UPDATE", "replication_pack", row.id, f"更新复制资产包《{row.title}》"
    )
    db.commit()
    db.refresh(row)
    return replication_service.pack_out(db, row)
