"""横向交接是原SIPOC产物的用途与本人确认，不是第二主库。"""

from copy import deepcopy
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.timeutil import utcnow
from app.models.process import ProcessArch
from app.models.project import Project
from app.models.tool import Tool
from app.models.tool_sheet import ToolSheet
from app.models.user import User
from app.services import audit, charter, org_access, process_scope


def label(data):
    if not data:
        return "未记录横向交接"
    confirmations = data.get("confirmations") or {}
    if any(row.get("decision") == "REJECT" for row in confirmations.values()):
        return "存在异议"
    if all(side in confirmations for side in ("provider", "receiver")):
        return "双方已确认"
    if "provider" in confirmations:
        return "待接收方确认"
    if "receiver" in confirmations:
        return "待提供方确认"
    return "待双方确认"


def prepare(db, user, tool, process, payload):
    if payload is None:
        return None
    if tool.code != "SIPOC":
        raise HTTPException(400, "横向交接请使用原SIPOC产物")
    receiver = db.get(ProcessArch, payload.receiver_process_id)
    if receiver is None or receiver.is_draft:
        raise HTTPException(400, "接收流程不存在或仍为草稿")
    for field in ("provider_user_id", "receiver_user_id"):
        person = db.get(User, getattr(payload, field))
        if person is None or not person.is_active:
            raise HTTPException(400, "参与账号不存在或已停用")
    for field in ("quality", "timing", "exception_path"):
        if not getattr(payload, field).strip():
            raise HTTPException(400, "质量、时间和例外处理都要写明")
    ids = process_scope.ancestor_ids(db, process.id) | process_scope.ancestor_ids(db, receiver.id)
    charter.document_ref(db, user, payload.standard_version_id, ids)
    return {**payload.model_dump(), "confirmations": {}}


def require_sheet(db, user, code, sheet_id, _seen=None):
    seen = set(_seen or ())
    if sheet_id in seen:
        raise HTTPException(400, "原作业引用成环")
    seen.add(sheet_id)
    row = db.get(ToolSheet, sheet_id)
    if row is None or row.tool_code != code:
        raise HTTPException(404, "方法记录不存在")
    if row.project_id:
        project = db.get(Project, row.project_id)
        if project:
            org_access.ensure_visible(db, user, project.org_unit_id)
    if (row.work_context or {}).get("round_id"):
        from app.services import improvement_round

        improvement_round.require(db, user, row.process_id, row.work_context["round_id"])
    if row.handoff:
        version_id = row.handoff.get("standard_version_id")
        if version_id:
            from app.models.process_document import ProcessDocument, ProcessDocumentVersion

            version = db.get(ProcessDocumentVersion, version_id)
            document = db.get(ProcessDocument, version.document_id) if version else None
            if document:
                org_access.ensure_visible(db, user, document.org_unit_id)
    upstream = (row.work_context or {}).get("upstream_sheet_id")
    if upstream:
        parent = db.get(ToolSheet, upstream)
        if parent is None or parent.process_id != row.process_id:
            raise HTTPException(404, "原上游作业不存在")
        require_sheet(db, user, parent.tool_code, parent.id, seen)
    return row


def detail(db, user, code, sheet_id):
    from app.services.tool_sheet import _out

    row = require_sheet(db, user, code, sheet_id)
    tool = db.scalar(select(Tool).where(Tool.code == code))
    return _out(db, row, tool.name if tool else code, [])


def confirm(db, user, code, sheet_id, payload):
    row = require_sheet(db, user, code, sheet_id)
    if row.handoff is None:
        raise HTTPException(400, "该方法记录没有横向交接")
    if row.revision != payload.expected_revision:
        raise HTTPException(409, "交接记录已更新，请刷新后重试")
    if row.handoff.get(payload.side + "_user_id") != user.id:
        raise HTTPException(403, "只能由指定参与者本人确认，不允许代签")
    if not payload.evidence.strip():
        raise HTTPException(400, "请写明本次决定的核验依据")
    data = deepcopy(row.handoff)
    data.setdefault("confirmations", {})[payload.side] = {
        "decision": payload.decision,
        "evidence": payload.evidence.strip(),
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
    }
    result = db.execute(
        update(ToolSheet)
        .where(ToolSheet.id == row.id, ToolSheet.revision == payload.expected_revision)
        .values(handoff=data, revision=row.revision + 1, updated_at=utcnow())
    )
    if result.rowcount != 1:
        raise HTTPException(409, "交接记录已更新，请刷新后重试")
    audit.record(
        db,
        user,
        "UPDATE",
        "tool_sheet",
        row.id,
        f"交接{payload.side}本人确认：{payload.decision}；{payload.evidence.strip()}",
    )
    db.commit()
    db.expire(row)
    return detail(db, user, code, sheet_id)


def for_process(db, user, process_id):
    rows = db.scalars(
        select(ToolSheet)
        .where(ToolSheet.tool_code == "SIPOC", ToolSheet.handoff.is_not(None))
        .order_by(ToolSheet.id.desc())
    ).all()
    result = []
    for row in rows:
        if not row.handoff or (
            row.process_id != process_id and row.handoff.get("receiver_process_id") != process_id
        ):
            continue
        try:
            result.append(detail(db, user, "SIPOC", row.id))
        except HTTPException as exc:
            if exc.status_code != 404:
                raise
    return result
