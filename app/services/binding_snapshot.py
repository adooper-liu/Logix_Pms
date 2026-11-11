"""原模型绑定依据快照：内容哈希，不提交事务，不依查看者裁剪固定内容。"""

import hashlib
import json
from datetime import date, datetime

from sqlalchemy import or_, select

from app.core.timeutil import utcnow
from app.models.adoption import ProcessTrainingRecord
from app.models.asset_graph import EvidenceClaim, NodeActivityLink
from app.models.execution import FormDefinition, ProcessRule
from app.models.monitor import KpiDefinition
from app.models.org import Position
from app.models.process import NodeTool, ProcessArch, ProcessNode
from app.models.process_document import ProcessDocument
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.resource_link import ActivityResourceLink
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.workload import WorkMeasurementStandard
from app.services import process_model, resource_link
from app.services.process_document import effective_version_on

LABELS = {
    "CONFIRMED": "绑定与固定依据一致",
    "PENDING_CONFIRM": "绑定待确认",
    "STALE": "原绑定已删除或失效",
}


def _value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _row(row):
    return {
        c.name: _value(getattr(row, c.name))
        for c in row.__table__.columns
        if c.name not in {"created_at", "updated_at"}
    }


def _hash(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def capture(db, process, version):
    nodes = (
        (version.snapshot or {}).get("nodes", [])
        if version
        else process_model.current_snapshot(db, process.id).get("nodes", [])
    )
    activities = list(
        db.scalars(
            select(ProcessArch).where(
                ProcessArch.parent_id == process.id,
                ProcessArch.level == 4,
                ProcessArch.is_draft.is_(False),
            )
        ).all()
    )
    if process.level == 4 and not process.is_draft:
        activities = [process]
    links = list(
        db.scalars(
            select(NodeActivityLink).where(
                NodeActivityLink.process_id == process.id,
                or_(
                    NodeActivityLink.model_version_id == version.id if version else False,
                    NodeActivityLink.model_version_id.is_(None),
                ),
            )
        ).all()
    )

    def process_rows(cls):
        return list(db.scalars(select(cls).where(cls.process_id == process.id)).all())

    racis = process_rows(RaciAssignment)
    forms = process_rows(FormDefinition)
    rules = process_rows(ProcessRule)
    tools = process_rows(NodeTool)
    training = process_rows(ProcessTrainingRecord)
    claims = process_rows(EvidenceClaim)
    kpis = list(
        db.scalars(
            select(KpiDefinition).where(
                or_(
                    KpiDefinition.process_id == process.id,
                    KpiDefinition.activity_id.in_([a.id for a in activities]),
                )
            )
        ).all()
    )
    documents = list(
        db.scalars(
            select(ProcessDocument).where(
                ProcessDocument.process_id.in_([process.id] + [a.id for a in activities])
            )
        ).all()
    )
    resources = list(
        db.scalars(
            select(ActivityResourceLink).where(
                ActivityResourceLink.activity_id.in_([a.id for a in activities]),
                ActivityResourceLink.is_active.is_(True),
            )
        ).all()
    )
    result = {}
    ancestors = {process.id}
    parent_id = process.parent_id
    while parent_id and parent_id not in ancestors:
        ancestors.add(parent_id)
        parent = db.get(ProcessArch, parent_id)
        parent_id = parent.parent_id if parent else None
    objective_links = list(
        db.scalars(
            select(ObjectiveProcessLink).where(
                ObjectiveProcessLink.process_id.in_(ancestors | {a.id for a in activities})
            )
        ).all()
    )
    node_keys = {
        node.id: node.node_key
        for node in db.scalars(
            select(ProcessNode).where(ProcessNode.process_id == process.id)
        ).all()
    }
    day = utcnow().date()
    for activity in activities:
        related = []
        for node in nodes:
            mappings = [
                link.activity_id
                for link in links
                if link.node_key == node["node_key"] and link.relation in {"REALIZES", "PART_OF"}
            ]
            if activity.id in (mappings or [node.get("process_arch_id")]):
                related.append(node)
        keys = {n["node_key"] for n in related}
        entries = {}
        invalid = []

        def add(kind, row, extra=None, valid=True, entries=entries, invalid=invalid):
            key = f"{kind}:{row.id}"
            entries[key] = {
                "hash": _hash({"data": _row(row), "extra": extra or {}}),
                "valid": bool(valid),
            }
            if not valid:
                invalid.append(key)

        for node in related:
            entries["NODE:" + node["node_key"]] = {"data": node, "extra": {}, "valid": True}
            pid = node.get("owner_position_id")
            if pid:
                position = db.get(Position, pid)
                if position:
                    add("POSITION", position, valid=position.is_active)
        for row in links:
            if row.activity_id == activity.id:
                add("MAPPING", row)
        for row in racis:
            if (
                row.activity_id == activity.id
                or row.activity_id is None
                and (not row.node_key or row.node_key in keys)
            ):
                role = db.get(GovernanceRole, row.role_id)
                from app.services.position_coverage import role_position

                members = (
                    [
                        {
                            "member_id": m.id,
                            "user_id": m.user_id,
                            "user_active": bool(m.user and m.user.is_active),
                            "position_id": m.user.position_id if m.user else None,
                            "position_active": bool(
                                m.user
                                and m.user.position_id
                                and (pos := db.get(Position, m.user.position_id))
                                and pos.is_active
                            ),
                        }
                        for m in sorted(role.members, key=lambda member: member.id)
                    ]
                    if role
                    else []
                )
                add(
                    "RACI",
                    row,
                    {"role": _row(role) if role else {}, "members": members},
                    valid=bool(
                        role
                        and role.is_active
                        and (
                            row.activity_id is None
                            and not row.node_key
                            or role_position(db, role) is not None
                        )
                    ),
                )
        for row in resources:
            if row.activity_id != activity.id:
                continue
            valid, _, _ = resource_link.source(
                db,
                process,
                activity,
                row.resource_type,
                row.ref_id,
                row.node_key,
                model_version=version,
            )
            source_model = resource_link.MODELS.get(row.resource_type)
            original = db.get(source_model, row.ref_id) if source_model and row.ref_id else None
            extra = _row(original) if original else {}
            if isinstance(original, ProcessDocument):
                ver = effective_version_on(original, day)
                extra["effective_version"] = _row(ver) if ver else None
            add("RESOURCE_LINK", row, extra, valid)
        for kind, rows in [("FORM", forms), ("RULE", rules), ("TOOL", tools)]:
            for row in rows:
                if (not getattr(row, "node_key", None) or row.node_key in keys) and getattr(
                    row, "is_active", True
                ):
                    add(kind, row)
        for link in objective_links:
            objective = db.get(StrategyObjective, link.objective_id)
            if link.process_id in ancestors | {activity.id} and objective:
                add("OBJECTIVE_LINK", link, _row(objective), valid=objective.status == "ACTIVE")
        for row in kpis:
            if row.is_active and (
                row.activity_id == activity.id
                or row.activity_id is None
                and row.process_id == process.id
            ):
                add(
                    "KPI",
                    row,
                    valid=(row.valid_to is None or row.valid_to >= day)
                    and (row.valid_from is None or row.valid_from <= day),
                )
        for row in documents:
            # 编译产物是投影，不反向成为自己的输入；显式资源引用仍在上方捕获。
            if any(v.source_kind == "COMPILED" for v in row.versions):
                continue
            if row.is_active and (
                row.process_id == activity.id
                and not row.node_key
                or row.process_id == process.id
                and (not row.node_key or row.node_key in keys)
            ):
                ver = effective_version_on(row, day)
                add(
                    "DOCUMENT",
                    row,
                    {"effective_version": _row(ver) if ver else None},
                    valid=ver is not None,
                )
        for row in db.scalars(
            select(WorkMeasurementStandard).where(
                WorkMeasurementStandard.activity_id == activity.id
            )
        ).all():
            if row.status == "VERIFIED":
                add("WORK_STANDARD", row, valid=(row.valid_to is None or row.valid_to >= day))
        for row in training:
            add("TRAINING", row)
        for row in claims:
            if any(
                (
                    t.target_type in {"ACTIVITY", "TIME_FIELD"}
                    and t.target_id == activity.id
                    or t.target_type == "NODE"
                    and node_keys.get(t.target_id) in keys
                )
                and (t.model_version_id is None or version and t.model_version_id == version.id)
                for t in row.targets
            ):
                from app.services import evidence_source

                original = evidence_source.resolve(db, process, row)
                extra = {
                    "targets": [_row(t) for t in row.targets],
                    "source": _row(original) if original is not None else None,
                }
                add(
                    "EVIDENCE",
                    row,
                    extra,
                    valid=original is not None
                    and row.status != "EXPIRED"
                    and (row.valid_to is None or row.valid_to >= day)
                    and (row.valid_from is None or row.valid_from <= day),
                )
        result[str(activity.id)] = {
            "entries": entries,
            "invalid": sorted(invalid),
            "hash": _hash(entries),
        }
    return {
        "rule_version": 1,
        "model_version_id": version.id if version else None,
        "captured_at": utcnow().isoformat() + "+00:00",
        "activities": result,
    }


def compare(current, basis):
    if basis is None:
        return "PENDING_CONFIRM"
    old = basis.get("activities", {})
    new = current["activities"]
    if set(old) - set(new):
        return "STALE"
    for aid, previous in old.items():
        present = new.get(aid, {}).get("entries", {})
        if set(previous.get("entries", {})) - set(present):
            return "STALE"
        if any(not item["valid"] for item in present.values()):
            return "STALE"
    if current.get("model_version_id") != basis.get("model_version_id") or _hash(new) != _hash(old):
        return "PENDING_CONFIRM"
    return "CONFIRMED"


def activity_scope(snapshot, activity_ids):
    """只裁剪活动字典；保留模型身份与每个活动的全部原来源。"""
    if snapshot is None or activity_ids is None:
        return snapshot
    return {
        **snapshot,
        "activities": {
            key: value
            for key, value in snapshot.get("activities", {}).items()
            if int(key) in activity_ids
        },
    }
