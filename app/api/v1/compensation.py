"""取消补偿与实例归档 API。"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.compensation import CompensationRecord
from app.schemas.compensation import (
    CompensationActionCreate,
    CompensationActionOut,
    CompensationCompleteIn,
    CompensationRecordOut,
)
from app.services import audit as audit_service
from app.services import compensation as compensation_service

router = APIRouter(tags=["取消补偿"])


@router.get(
    "/processes/{process_id}/compensations",
    response_model=List[CompensationActionOut],
    summary="节点的取消补偿动作",
)
def list_actions(process_id: int, db: DbSession, user: CurrentUser):
    return [
        compensation_service.action_out(row)
        for row in compensation_service.list_actions(db, process_id)
    ]


@router.post(
    "/processes/{process_id}/compensations",
    response_model=CompensationActionOut,
    summary="配置节点补偿动作（Manager）",
)
def upsert_action(
    process_id: int, payload: CompensationActionCreate, db: DbSession, user: ManagerUser
):
    try:
        row = compensation_service.upsert_action(db, process_id, payload.model_dump())
    except compensation_service.CompensationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "compensation_action",
        row.id,
        f"配置流程 {process_id} 节点 {row.node_key} 补偿动作",
    )
    db.commit()
    db.refresh(row)
    return compensation_service.action_out(row)


@router.get(
    "/execution/instances/{instance_id}/compensations",
    response_model=List[CompensationRecordOut],
    summary="实例的补偿待办",
)
def list_records(instance_id: int, db: DbSession, user: CurrentUser):
    return [
        compensation_service.record_out(row)
        for row in compensation_service.records_for_instance(db, instance_id)
    ]


@router.post(
    "/execution/compensations/{record_id}/complete",
    response_model=CompensationRecordOut,
    summary="完成补偿（Manager）",
)
def complete_record(
    record_id: int, payload: CompensationCompleteIn, db: DbSession, user: ManagerUser
):
    row = db.get(CompensationRecord, record_id)
    if row is None:
        raise HTTPException(status_code=404, detail="补偿记录不存在")
    try:
        compensation_service.complete_record(db, row, user, payload.note)
    except compensation_service.CompensationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, user, "UPDATE", "compensation_record", row.id, f"完成补偿 {row.action_name}"
    )
    db.commit()
    db.refresh(row)
    return compensation_service.record_out(row)


@router.post("/execution/instances/archive", summary="归档已完成/已取消实例（Manager）")
def archive_instances(
    db: DbSession,
    user: ManagerUser,
    older_than_days: int = Query(default=365, ge=1, le=3650),
):
    try:
        count = compensation_service.archive_instances(db, older_than_days)
    except compensation_service.CompensationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_instance",
        None,
        f"归档 {older_than_days} 天前完成/取消的实例 {count} 个",
    )
    db.commit()
    return {"archived": count}
