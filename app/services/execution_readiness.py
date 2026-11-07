"""上线准备读取原发布/运行配置，决定随配置指纹失效。"""

from copy import deepcopy
from datetime import timezone

from fastapi import HTTPException
from sqlalchemy import select, update

from app.core.timeutil import utcnow
from app.models.execution import NodeAssignment, ProcessExecutionConfig
from app.models.process import ProcessArch, ProcessModelVersion, ProcessNode
from app.models.user import User
from app.services import audit, execution, forms, improvement_round, process_model

REQUIREMENTS = {"forms": "结构化任务表单", "assignments": "节点分派", "deadlines": "办理时限"}
LIMITATIONS = [
    "当前轻量执行器仅支持已验证的串行/排他子集；Flowable、并行/子流程/事件接入尚未交付。",
    "准备确认只针对当前原发布/配置及适用性，不等于组织业务授权、实际运行有效或改善达标。",
    "RPA/案例/新技术并非通用上线必需；登记、端点HTTP成功和实际业务结果分开。",
]


def require_process(db, pid):
    row = db.get(ProcessArch, pid)
    if row is None:
        raise HTTPException(404, "流程不存在")
    return row


def published(db, process):
    return db.scalar(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.version == process.published_model_version,
            ProcessModelVersion.published_at.is_not(None),
            ProcessModelVersion.status.in_(("PUBLISHED", "SUPERSEDED")),
        )
    )


def basis(db, process):
    version = published(db, process)
    config = execution.get_execution_config(db, process.id)
    assignments = db.scalars(
        select(NodeAssignment)
        .where(NodeAssignment.process_id == process.id, NodeAssignment.is_active.is_(True))
        .order_by(NodeAssignment.id)
    ).all()
    nodes = db.scalars(
        select(ProcessNode).where(
            ProcessNode.process_id == process.id,
            ProcessNode.node_type.notin_(("START", "END", "PARALLEL")),
        )
    ).all()
    configured = {a.node_key: a for a in assignments}
    eligibility = {}
    for a in assignments:
        handler = db.get(User, a.default_assignee_user_id) if a.default_assignee_user_id else None
        eligibility[a.node_key] = bool(
            a.role
            or a.org_unit_id
            or (handler and handler.is_active and handler.role in ("ADMIN", "MANAGER", "OWNER"))
        )
    snapshot = {
        "model": version.id if version else None,
        "model_hash": improvement_round.model_hash(version) if version else None,
        "forms": forms.form_snapshot(db, process.id),
        "rules": forms.rule_snapshot(db, process.id),
        "assignments": [
            {
                key: getattr(a, key)
                for key in (
                    "node_key",
                    "role",
                    "org_unit_id",
                    "default_assignee_user_id",
                    "due_hours",
                    "escalation_hours",
                    "escalation_user_id",
                )
            }
            for a in assignments
        ],
        "assignment_eligibility": eligibility,
        "config": {
            key: getattr(config, key) if config else None
            for key in (
                "default_task_due_hours",
                "default_escalation_hours",
                "default_escalation_user_id",
            )
        },
    }
    node_facts = [
        {
            "node_key": n.node_key,
            "name": n.name,
            "facts": {
                "forms": bool(forms.form_for_snapshot({"forms": snapshot["forms"]}, n.node_key)),
                "assignments": eligibility.get(n.node_key, False),
                "deadlines": bool(
                    (configured.get(n.node_key) and configured[n.node_key].due_hours is not None)
                    or (config and config.default_task_due_hours is not None)
                ),
            },
        }
        for n in nodes
    ]
    facts = {
        key: bool(node_facts) and all(n["facts"][key] for n in node_facts) for key in REQUIREMENTS
    }
    return version, config, snapshot, facts, node_facts


def get(db, user, pid):
    process = require_process(db, pid)
    version, config, snapshot, facts, nodes = basis(db, process)
    data = config.readiness if config else None
    fingerprint = improvement_round.digest(snapshot)
    missing = []
    if version is None:
        missing.append("没有真实当前发布模型")
    if data is None:
        missing.append("尚未记录准备约定")
    else:
        for key, label in REQUIREMENTS.items():
            requirement = data.get("requirements", {}).get(key)
            if not requirement:
                missing.append(label + "适用性未约定")
            else:
                failures = []
                for node in nodes:
                    req = (
                        data.get("node_requirements", {})
                        .get(node["node_key"], {})
                        .get(key, requirement)
                    )
                    if req["mode"] == "REQUIRED" and not node["facts"][key]:
                        failures.append(node["name"])
                if failures or (not nodes and requirement["mode"] == "REQUIRED"):
                    missing.append(label + "未完整配置")
        current_keys = {n["node_key"] for n in nodes}
        if set(data.get("node_requirements", {})) - current_keys:
            missing.append("原任务适用性引用已变化，请修订准备约定")
    decision = (data or {}).get("confirmation")
    current = bool(decision and decision.get("fingerprint") == fingerprint)
    confirmed = bool(current and decision.get("decision") == "ACCEPT" and not missing)
    state = "准备约定待本人确认"
    if confirmed:
        state = "当前发布与准备约定已确认"
    elif decision and not current:
        state = "准备依据已变化，待复核"
    elif decision and decision.get("decision") == "RETURN":
        state = "准备已退回补证"
    if data is None:
        state = "准备约定未记录"
    reviewers = db.scalars(
        select(User)
        .where(User.is_active.is_(True), User.role != "VIEWER")
        .order_by(User.display_name)
    ).all()
    return {
        "process_id": pid,
        "published_model_version_id": version.id if version else None,
        "revision": config.readiness_revision if config else 0,
        "readiness": data,
        "confirmed": confirmed,
        "state_label": state,
        "missing": missing,
        "fingerprint": fingerprint,
        "limitations": LIMITATIONS,
        "reviewers": [{"id": u.id, "name": u.display_name} for u in reviewers],
        "facts": facts,
        "nodes": nodes,
        "requirement_labels": REQUIREMENTS,
        "mode_labels": {"REQUIRED": "必需", "NOT_APPLICABLE": "不适用"},
        "decision_labels": {"ACCEPT": "确认准备", "RETURN": "退回补证"},
    }


def config_row(db, pid):
    row = execution.get_execution_config(db, pid)
    if row is None:
        row = ProcessExecutionConfig(process_id=pid)
        db.add(row)
        db.flush()
    return row


def update_config(db, user, pid, payload):
    process = require_process(db, pid)
    process_model.lock_process(db, process)
    if set(payload.requirements) != set(REQUIREMENTS):
        raise HTTPException(400, "表单/分派/时限适用性须分别约定")
    nodes = basis(db, process)[4]
    if not set(payload.node_requirements) <= {n["node_key"] for n in nodes}:
        raise HTTPException(400, "任务适用性只能引用当前原发布任务")
    for requirements in payload.node_requirements.values():
        if not set(requirements) <= set(REQUIREMENTS):
            raise HTTPException(400, "任务适用性条件无效")
    for req in list(payload.requirements.values()) + [
        req for items in payload.node_requirements.values() for req in items.values()
    ]:
        if req.mode == "NOT_APPLICABLE" and not req.reason.strip():
            raise HTTPException(400, "不适用必须写明依据")
    reviewer = db.get(User, payload.reviewer_user_id)
    if (
        reviewer is None
        or not reviewer.is_active
        or reviewer.role == "VIEWER"
        or reviewer.id == user.id
    ):
        raise HTTPException(400, "请选择另一位可办理接收者")
    if not payload.evidence.strip() or not payload.rollback_note.strip():
        raise HTTPException(400, "核对依据与回退准备不可为空")
    row = config_row(db, pid)
    if row.readiness_revision != payload.expected_revision:
        raise HTTPException(409, "准备约定已变化，请刷新")
    data = payload.model_dump(mode="json", exclude={"expected_revision"})
    data["edited_by_id"] = user.id
    result = db.execute(
        update(ProcessExecutionConfig)
        .where(
            ProcessExecutionConfig.id == row.id,
            ProcessExecutionConfig.readiness_revision == payload.expected_revision,
        )
        .values(readiness=data, readiness_revision=payload.expected_revision + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "准备约定已变化，请刷新")
    audit.record(db, user, "UPDATE", "execution_readiness", pid, "修订原上线准备约定（清本人决定）")
    db.commit()
    db.expire(row)
    return get(db, user, pid)


def confirm(db, user, pid, payload):
    process = require_process(db, pid)
    process_model.lock_process(db, process)
    row = execution.get_execution_config(db, pid)
    if row is None or not row.readiness:
        raise HTTPException(400, "请先记录上线准备约定")
    if row.readiness_revision != payload.expected_revision:
        raise HTTPException(409, "准备约定已变化，请刷新")
    data = deepcopy(row.readiness)
    if data.get("reviewer_user_id") != user.id or data.get("edited_by_id") == user.id:
        raise HTTPException(403, "仅指定非编辑者可本人确认，不允许代签")
    if not payload.evidence.strip():
        raise HTTPException(400, "请写明本人核对依据")
    current = get(db, user, pid)
    if payload.decision == "ACCEPT" and current["missing"]:
        raise HTTPException(400, "准备缺项：" + "；".join(current["missing"]))
    data["confirmation"] = {
        "decision": payload.decision,
        "evidence": payload.evidence.strip(),
        "user_id": user.id,
        "name": user.display_name,
        "at": utcnow().replace(tzinfo=timezone.utc).isoformat(),
        "model_version_id": current["published_model_version_id"],
        "fingerprint": current["fingerprint"],
    }
    result = db.execute(
        update(ProcessExecutionConfig)
        .where(
            ProcessExecutionConfig.id == row.id,
            ProcessExecutionConfig.readiness_revision == payload.expected_revision,
        )
        .values(readiness=data, readiness_revision=payload.expected_revision + 1)
    )
    if result.rowcount != 1:
        raise HTTPException(409, "准备约定已变化，请刷新")
    audit.record(
        db,
        user,
        "UPDATE",
        "execution_readiness",
        pid,
        "本人准备决定：" + payload.decision + "；" + payload.evidence,
    )
    db.commit()
    db.expire(row)
    return get(db, user, pid)
