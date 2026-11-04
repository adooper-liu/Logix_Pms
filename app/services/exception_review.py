"""原异常的行动约定和本人效果核验。"""

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.timeutil import utcnow
from app.models.monitor import ExceptionEvent
from app.models.user import User
from app.services import audit, org_access


def validate_source(db, user, payload):
    from app.models.execution import ProcessInstance
    from app.models.monitor import KpiDefinition
    from app.models.process import ProcessArch
    from app.models.project import Project
    from app.services import process_model

    if payload.project_id:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(404, "项目不存在")
        org_access.ensure_visible(db, user, project.org_unit_id)
        if project.process_id != payload.process_id:
            raise HTTPException(400, "异常项目与流程不一致")
    process = db.get(ProcessArch, payload.process_id) if payload.process_id else None
    if payload.process_id and process is None:
        raise HTTPException(404, "流程不存在")
    if process:
        process_model.lock_process(db, process)
    for ident, model in (
        (payload.source_kpi_id, KpiDefinition),
        (payload.source_instance_id, ProcessInstance),
    ):
        if ident:
            source = db.get(model, ident)
            if source is None:
                raise HTTPException(404, "异常来源不存在")
            if source.process_id != payload.process_id:
                raise HTTPException(400, "异常来源与流程不一致")
            if model is ProcessInstance and source.project_id:
                project = db.get(Project, source.project_id)
                if project:
                    org_access.ensure_visible(db, user, project.org_unit_id)


def visible_stmt(db, user):
    from sqlalchemy import or_

    from app.models.execution import ProcessInstance
    from app.models.project import Project

    project_ids = org_access.restrict(select(Project.id), db, user, Project.org_unit_id)
    visible_instances = select(ProcessInstance.id).where(
        or_(ProcessInstance.project_id.is_(None), ProcessInstance.project_id.in_(project_ids))
    )
    return select(ExceptionEvent).where(
        or_(ExceptionEvent.project_id.is_(None), ExceptionEvent.project_id.in_(project_ids)),
        or_(
            ExceptionEvent.source_instance_id.is_(None),
            ExceptionEvent.source_instance_id.in_(visible_instances),
        ),
    )


def require(db, user, ident):
    row = db.scalar(visible_stmt(db, user).where(ExceptionEvent.id == ident))
    if row is None:
        raise HTTPException(404, "异常事件不存在")
    if row.project_id:
        from app.models.project import Project

        project = db.get(Project, row.project_id)
        if project:
            org_access.ensure_visible(db, user, project.org_unit_id)
    db.execute(select(ExceptionEvent.id).where(ExceptionEvent.id == ident).with_for_update())
    db.refresh(row)
    return row


def prepare_update(db, user, row, data, expected):
    if expected is not None and expected != row.revision:
        raise HTTPException(409, "异常已变化，请刷新")
    if data.get("status") == "CLOSED":
        raise HTTPException(400, "措施效果须指定本人核验，不允许直接关闭")
    resolution = data.get("resolution")
    if resolution:
        reviewer = db.get(User, resolution["reviewer_user_id"])
        if (
            reviewer is None
            or not reviewer.is_active
            or reviewer.role == "VIEWER"
            or reviewer.id == user.id
        ):
            raise HTTPException(400, "请选择非编辑者本人核验")
        if any(
            not str(resolution[k]).strip()
            for k in ("decision", "action_ref", "evidence", "expected_result")
        ):
            raise HTTPException(400, "处置和核验约定不可为空")
        resolution = {
            **resolution,
            "edited_by_id": user.id,
            "basis": {
                "kpi_id": row.source_kpi_id,
                "instance_id": row.source_instance_id,
                "process_id": row.process_id,
                "project_id": row.project_id,
            },
        }
        if row.source_kpi_id:
            from app.models.monitor import KpiDefinition
            from app.services.kpi import latest_of

            kpi = db.get(KpiDefinition, row.source_kpi_id)
            record = latest_of(kpi.records) if kpi else None
            resolution["basis"]["sample"] = (
                {
                    "id": record.id,
                    "value": record.value,
                    "provenance": record.provenance,
                    "period": record.period.isoformat(),
                }
                if record
                else None
            )
        data["resolution"] = resolution
    elif row.resolution and any(
        k in data for k in ("action_taken", "root_cause", "status", "owner_user_id")
    ):
        resolution = deepcopy(row.resolution)
        resolution.pop("review", None)
        if any(k in data for k in ("action_taken", "root_cause", "owner_user_id")):
            resolution["edited_by_id"] = user.id
        data["resolution"] = resolution
    if row.status == "CLOSED" and "resolution" in data:
        data["status"] = "IN_PROGRESS"
        data["closed_at"] = None
        data["resolved_at"] = None
    data["revision"] = row.revision + 1


def review(db, user, ident, payload):
    row = require(db, user, ident)
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "异常已变化，请刷新")
    data = deepcopy(row.resolution or {})
    if data.get("reviewer_user_id") != user.id or data.get("edited_by_id") == user.id:
        raise HTTPException(403, "仅指定非编辑者本人可核验")
    if row.status != "RESOLVED" or not row.action_taken:
        raise HTTPException(400, "请先记录已执行措施并标记解决")
    if not payload.evidence.strip() or not payload.result.strip():
        raise HTTPException(400, "核验依据与结果不可为空")
    data["review"] = {
        "decision": payload.decision,
        "evidence": payload.evidence,
        "result": payload.result,
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().isoformat() + "+00:00",
    }
    values = {
        "resolution": data,
        "revision": row.revision + 1,
        "status": "CLOSED" if payload.decision == "ACCEPT" else "IN_PROGRESS",
        "closed_at": utcnow() if payload.decision == "ACCEPT" else None,
    }
    result = db.execute(
        update(ExceptionEvent)
        .where(ExceptionEvent.id == ident, ExceptionEvent.revision == payload.expected_revision)
        .values(**values)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "异常已变化，请刷新")
    audit.record(
        db,
        user,
        "UPDATE",
        "exception",
        ident,
        "本人效果核验：" + payload.decision + "；" + payload.evidence,
    )
    db.commit()
    db.refresh(row)
    return row
