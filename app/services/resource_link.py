"""活动原资源链接：统一引用，不复制原表单/规则/文件。"""

import re

from fastapi import HTTPException
from sqlalchemy import select

from app.core.timeutil import utcnow
from app.models.adoption import ProcessTechnologyUse, RpaBot
from app.models.execution import FormDefinition, ProcessRule
from app.models.integration import IntegrationEndpoint
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument
from app.models.resource_link import ActivityResourceLink
from app.schemas.resource_link import ResourceLinkOut, ResourceOptionOut, ResourceOptionsOut
from app.services import org_access, process_model
from app.services.process_document import effective_version_on, visible_conditions

LABELS = {
    "FORM": "任务表单",
    "RULE": "分支规则",
    "DOCUMENT": "标准文件",
    "INTEGRATION": "集成端点",
    "TECH": "技术使用",
    "RPA": "机器人登记",
    "EQUIPMENT": "设备引用",
    "MEASURE": "量具引用",
}
MODELS = {
    "FORM": FormDefinition,
    "RULE": ProcessRule,
    "DOCUMENT": ProcessDocument,
    "INTEGRATION": IntegrationEndpoint,
    "TECH": ProcessTechnologyUse,
    "RPA": RpaBot,
}
PREFIXES = {"DOCUMENT": "DOC", "EQUIPMENT": "EQUIP", "MEASURE": "MEASURE"}


def require_process(db, pid):
    process = db.get(ProcessArch, pid)
    if not process or process.level != 3 or process.is_draft:
        raise HTTPException(400, "请选择正式L3流程")
    return process


def require_activity(db, process, aid, node_key=None, *, model_version=None):
    activity = db.get(ProcessArch, aid)
    if not activity or activity.level != 4 or activity.parent_id != process.id or activity.is_draft:
        raise HTTPException(400, "活动不属于当前流程或仍为草稿")
    if node_key:
        from sqlalchemy import or_

        from app.models.asset_graph import NodeActivityLink

        version = model_version or process_model.latest_version(db, process.id)
        snapshot = version.snapshot if version else process_model.current_snapshot(db, process.id)
        node = next(
            (n for n in (snapshot or {}).get("nodes", []) if n["node_key"] == node_key), None
        )
        ids = list(
            db.scalars(
                select(NodeActivityLink.activity_id).where(
                    NodeActivityLink.process_id == process.id,
                    NodeActivityLink.node_key == node_key,
                    NodeActivityLink.relation.in_({"REALIZES", "PART_OF"}),
                    or_(
                        NodeActivityLink.model_version_id == version.id if version else False,
                        NodeActivityLink.model_version_id.is_(None),
                    ),
                )
            ).all()
        )
        if not node or aid not in (ids or [node.get("process_arch_id")]):
            raise HTTPException(400, "节点不存在或未实现所选活动")
    return activity


def source(db, process, activity, kind, ref_id, node_key=None, user=None, *, model_version=None):
    """valid,label,note；不可见来源不给名称。删除/停用原对象后保留失效引用。"""
    if kind not in MODELS:
        return True, LABELS.get(kind, kind), "仅外部引用登记，未核验实物或适用性"
    if user and kind in {"FORM", "RULE", "TECH", "RPA", "INTEGRATION"}:
        try:
            org_access.ensure_visible(db, user, process.org_unit_id)
        except HTTPException:
            return False, "受限来源", "无权查看原流程业务资源"
    row = db.get(MODELS[kind], ref_id) if ref_id else None
    if row is None:
        return False, "原来源已失效", "原对象已删除或不存在"
    label = (
        getattr(row, "name", None)
        or getattr(row, "title", None)
        or getattr(row, "bot_name", None)
        or str(row.id)
    )
    if kind in {"FORM", "RULE"}:
        if row.process_id != process.id or (row.node_key and node_key and row.node_key != node_key):
            return False, "原来源不适用", "表单/规则不属于当前流程或节点"
        if row.node_key:
            try:
                require_activity(
                    db, process, activity.id, row.node_key, model_version=model_version
                )
            except HTTPException:
                return False, "原来源不适用", "原节点专属资源未实现所选活动"
    elif kind in {"TECH", "RPA"}:
        if row.process_id not in {process.id, activity.id}:
            return False, "原来源不适用", "技术/机器人登记不属于当前流程或活动"
    elif kind == "DOCUMENT":
        if row.process_id not in {process.id, activity.id} or (
            row.node_key and node_key and row.node_key != node_key
        ):
            return False, "原来源不适用", "文件不属于当前流程或活动"
        if row.process_id == activity.id and row.node_key:
            return False, "原来源不适用", "活动子模型节点文件不等于父流程节点文件"
        if row.node_key:
            try:
                require_activity(
                    db, process, activity.id, row.node_key, model_version=model_version
                )
            except HTTPException:
                return False, "原来源不适用", "原节点专属文件未实现所选活动"
        if user:
            stmt = select(ProcessDocument.id).where(ProcessDocument.id == row.id)
            condition = visible_conditions(db, process.org_unit_id)
            if condition is not None:
                stmt = stmt.where(condition)
            if not org_access.unrestricted(user):
                condition = visible_conditions(db, user.org_unit_id)
                stmt = (
                    stmt.where(condition)
                    if condition is not None
                    else stmt.where(ProcessDocument.org_unit_id.is_(None))
                )
            if db.scalar(stmt) is None:
                return False, "受限来源", "无权查看原文件或不适用当前组织"
        if effective_version_on(row, utcnow().date()) is None:
            return False, label, "原文件没有当前有效版本"
    if hasattr(row, "is_active") and not row.is_active:
        return False, label, "原对象已停用"
    return True, label, "引用原对象；不代替业务核验"


def out(db, process, row, user=None, *, model_version=None):
    activity = db.get(ProcessArch, row.activity_id)
    valid, label, note = source(
        db,
        process,
        activity,
        row.resource_type,
        row.ref_id,
        row.node_key,
        user,
        model_version=model_version,
    )
    document = db.get(ProcessDocument, row.ref_id) if row.resource_type == "DOCUMENT" else None
    form = db.get(FormDefinition, row.ref_id) if row.resource_type == "FORM" else None
    record_carrier = valid and (
        form is not None
        and bool(form.node_key)
        or document is not None
        and document.category in {"FORM", "CHECKLIST"}
        and (bool(document.node_key) or document.process_id == activity.id)
    )
    return ResourceLinkOut(
        is_record_carrier=bool(record_carrier),
        id=row.id,
        activity_id=row.activity_id,
        resource_type=row.resource_type,
        resource_type_label=LABELS[row.resource_type],
        ref_id=row.ref_id,
        ref_key=row.ref_key,
        org_scope=row.org_scope,
        node_key=row.node_key,
        note=None if label == "受限来源" else row.note,
        is_active=row.is_active,
        source_valid=valid,
        source_status="CURRENT" if valid else "STALE",
        source_label=label,
        source_note=note,
        created_at=row.created_at,
    )


def list_links(db, process, user=None, *, model_version=None):
    rows = db.scalars(
        select(ActivityResourceLink)
        .join(ProcessArch, ProcessArch.id == ActivityResourceLink.activity_id)
        .where(ProcessArch.parent_id == process.id, ActivityResourceLink.is_active.is_(True))
        .order_by(ActivityResourceLink.id)
    ).all()
    return [out(db, process, row, user, model_version=model_version) for row in rows]


def upsert(db, process, payload, user):
    process_model.lock_process(db, process)
    activity = require_activity(db, process, payload.activity_id, payload.node_key)
    kind = payload.resource_type
    prefix = PREFIXES.get(kind, kind)
    if kind in MODELS:
        if payload.ref_id is None:
            raise HTTPException(400, "请选择已有原资源")
        ref_key = f"{prefix}:{payload.ref_id}"
        if payload.ref_key and payload.ref_key != ref_key:
            raise HTTPException(400, "引用键与原资源ID不一致")
        valid, _, note = source(db, process, activity, kind, payload.ref_id, payload.node_key, user)
        if not valid:
            raise HTTPException(400, note)
    else:
        ref_key = payload.ref_key or ""
        if payload.ref_id is not None or not re.fullmatch(
            re.escape(prefix) + r":[A-Za-z0-9][A-Za-z0-9_.:/-]{0,100}", ref_key
        ):
            raise HTTPException(400, "外部设备/量具只接受规范引用键")
    # GLOBAL 或确切组织ID，不猜自由文本范围。
    if payload.org_scope != "GLOBAL" and payload.org_scope != str(process.org_unit_id):
        raise HTTPException(400, "组织范围须为GLOBAL或当前流程组织ID")
    row = db.scalar(
        select(ActivityResourceLink).where(
            ActivityResourceLink.activity_id == activity.id,
            ActivityResourceLink.ref_key == ref_key,
            ActivityResourceLink.org_scope == payload.org_scope,
        )
    )
    if row is None:
        row = ActivityResourceLink(
            activity_id=activity.id,
            resource_type=kind,
            ref_id=payload.ref_id,
            ref_key=ref_key,
            org_scope=payload.org_scope,
            created_by_id=user.id,
        )
        db.add(row)
    row.node_key = payload.node_key
    row.note = payload.note
    row.is_active = True
    db.flush()
    return row


def deactivate(db, process, link_id):
    process_model.lock_process(db, process)
    row = db.get(ActivityResourceLink, link_id)
    if row is None or db.get(ProcessArch, row.activity_id).parent_id != process.id:
        raise HTTPException(404, "资源链接不存在")
    row.is_active = False
    db.flush()
    return row


def options(db, process, aid, node_key, user):
    activity = require_activity(db, process, aid, node_key)
    result = []
    for kind, model in MODELS.items():
        stmt = select(model)
        if hasattr(model, "process_id"):
            stmt = stmt.where(model.process_id.in_({process.id, activity.id}))
        for row in db.scalars(stmt.order_by(model.id)).all():
            valid, label, _ = source(db, process, activity, kind, row.id, node_key, user)
            if valid:
                result.append(
                    ResourceOptionOut(
                        resource_type=kind,
                        resource_type_label=LABELS[kind],
                        ref_id=row.id,
                        ref_key=f"{PREFIXES.get(kind, kind)}:{row.id}",
                        label=label,
                    )
                )
    return ResourceOptionsOut(resource_type_labels=LABELS, options=result)
