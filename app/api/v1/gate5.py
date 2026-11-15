"""Generic Gate 5 responsibility closure API."""

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.models.responsibility import ProcessResponsibilityAcceptance
from app.schemas.gate5 import (
    AcceptanceCreate,
    AccountabilityUpdate,
    AssignmentUpdate,
    Gate5ReadinessOut,
    OwnerUpdate,
)
from app.services import audit
from app.services import gate5_readiness as service

router = APIRouter(prefix="/processes/{process_id}/gate5", tags=["Gate 5 责任闭合"])


def _process(db, process_id):
    return service._process(db, process_id)


@router.get("/readiness", response_model=Gate5ReadinessOut)
def gate5_readiness(
    process_id: int, db: DbSession, user: CurrentUser, model_version_id: int | None = None
):
    return service.readiness(db, process_id, model_version_id=model_version_id, viewer=user)


@router.put("/owner")
def set_owner(process_id: int, payload: OwnerUpdate, db: DbSession, user: ManagerUser):
    process = _process(db, process_id)
    service.set_process_owner(
        db,
        process,
        owner_user_id=payload.owner_user_id,
        actor=user,
        expected_model_version_id=payload.expected_model_version_id,
    )
    db.commit()
    return {"process_id": process.id, "owner_user_id": process.owner_user_id}


@router.put("/assignments/{node_key}")
def set_assignment(
    process_id: int, node_key: str, payload: AssignmentUpdate, db: DbSession, user: WriteUser
):
    process = _process(db, process_id)
    if user.role == "OWNER" and process.owner_user_id != user.id:
        raise HTTPException(403, "只能维护自己负责的流程")
    row = service.upsert_assignment(
        db,
        process,
        node_key,
        payload.model_dump(exclude_unset=True, exclude={"expected_model_version_id"}),
        user,
        payload.expected_model_version_id,
    )
    db.commit()
    return {
        "id": row.id,
        "process_id": row.process_id,
        "node_key": row.node_key,
        "model_version_id": row.model_version_id,
    }


@router.put("/accountability/{node_key}")
def set_accountability(
    process_id: int, node_key: str, payload: AccountabilityUpdate, db: DbSession, user: ManagerUser
):
    process = _process(db, process_id)
    version = service._published(db, process)
    if version is None or version.id != payload.expected_model_version_id:
        raise HTTPException(409, "已发布模型版本已变化，请刷新")
    activity = next(
        (
            n.get("process_arch_id")
            for n in version.snapshot.get("nodes", [])
            if n.get("node_key") == node_key
        ),
        None,
    )
    if activity is None:
        raise HTTPException(404, "节点不属于当前模型")
    row = __import__("app.models.raci", fromlist=["RaciAssignment"]).RaciAssignment(
        process_id=process.id,
        activity_id=activity,
        matter=f"{node_key} 活动责任",
        node_key=node_key,
        role_id=payload.role_id,
        raci="A",
    )
    db.add(row)
    db.flush()
    audit.record(
        db, user, "CREATE", "raci_assignment", row.id, f"写入 {process.code}/{node_key} 活动 A"
    )
    db.commit()
    return {"id": row.id, "node_key": node_key, "activity_id": activity, "raci": row.raci}


@router.post("/acceptances")
def accept(process_id: int, payload: AcceptanceCreate, db: DbSession, user: WriteUser):
    process = _process(db, process_id)
    row = service.accept_responsibility(
        db,
        process,
        model_version_id=payload.model_version_id,
        node_key=payload.node_key,
        scope=payload.scope,
        subject_user_id=payload.subject_user_id,
        actor=user,
        valid_until=payload.valid_until,
        evidence_note=payload.evidence_note,
    )
    db.commit()
    return {
        "id": row.id,
        "status": row.status,
        "scope": row.scope,
        "model_version_id": row.model_version_id,
    }


@router.post("/acceptances/{acceptance_id}/withdraw")
def withdraw(process_id: int, acceptance_id: int, db: DbSession, user: WriteUser):
    process = _process(db, process_id)
    row = db.get(ProcessResponsibilityAcceptance, acceptance_id)
    if row is None or row.process_id != process.id:
        raise HTTPException(404, "责任接受记录不存在")
    if user.id != row.subject_user_id and user.role not in {"ADMIN", "MANAGER"}:
        raise HTTPException(403, "无权撤回该责任接受")
    row.status = "WITHDRAWN"
    audit.record(db, user, "UPDATE", "responsibility_acceptance", row.id, "撤回责任接受")
    db.commit()
    return {"id": row.id, "status": row.status}
