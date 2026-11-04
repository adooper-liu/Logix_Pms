"""复制资产包 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, WriteUser, ensure_can_edit_owned
from app.schemas.replication import (
    ReplicationPackCreate,
    ReplicationPackOut,
    ReplicationPackUpdate,
    ReplicationReceiptIn,
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
    result = []
    for row in replication_service.list_packs(
        db, source_project_id=source_project_id, status=status_, limit=limit
    ):
        try:
            replication_service.ensure_visible(db, user, row)
            result.append(replication_service.pack_out(db, row))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return result


@router.get("/{pack_id}", response_model=ReplicationPackOut, summary="复制资产包详情")
def get_pack(pack_id: int, db: DbSession, user: CurrentUser):
    row = db.get(replication_service.ReplicationPack, pack_id)
    if row is None:
        raise HTTPException(status_code=404, detail="复制资产包不存在")
    replication_service.ensure_visible(db, user, row)
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


@router.post("/{pack_id}/receipt", response_model=ReplicationPackOut)
def receive_pack(pack_id: int, payload: ReplicationReceiptIn, db: DbSession, user: WriteUser):
    from sqlalchemy import update

    from app.core.timeutil import utcnow
    from app.models.process import ProcessArch
    from app.models.project import Project
    from app.services import org_access

    row = db.get(replication_service.ReplicationPack, pack_id)
    if row is None:
        raise HTTPException(404, "复制包不存在")
    project = db.get(Project, row.source_project_id) if row.source_project_id else None
    if project:
        org_access.ensure_visible(db, user, project.org_unit_id)
    if row.receiver_user_id != user.id or row.owner_user_id == user.id:
        raise HTTPException(403, "仅指定非编制者可本人接收")
    if row.status != "PUBLISHED" or not row.source_snapshot:
        raise HTTPException(400, "请先发布有固定来源的复制包")
    target = db.get(ProcessArch, payload.target_process_id)
    if target is None:
        raise HTTPException(404, "目标流程不存在")
    ensure_can_edit_owned(user, target.owner_user_id, target.owner)
    if not payload.evidence.strip():
        raise HTTPException(400, "请填写本地核对依据")
    changed = db.execute(
        update(replication_service.ReplicationPack)
        .where(
            replication_service.ReplicationPack.id == pack_id,
            replication_service.ReplicationPack.revision == payload.expected_revision,
        )
        .values(
            receipt={
                "decision": payload.decision,
                "evidence": payload.evidence,
                "target_process_id": target.id,
                "user_id": user.id,
                "name": user.display_name,
                "at": utcnow().isoformat() + "+00:00",
            },
            revision=payload.expected_revision + 1,
        )
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "复制包已变化")
    audit_service.record(
        db,
        user,
        "UPDATE",
        "replication_pack",
        pack_id,
        "本人接收：" + payload.decision + "；" + payload.evidence,
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
