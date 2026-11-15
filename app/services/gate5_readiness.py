"""Generic Gate 5 responsibility readiness and safe configuration writes."""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.asset_graph import NodeActivityLink
from app.models.execution import NodeAssignment
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.responsibility import ProcessResponsibilityAcceptance
from app.models.user import User
from app.schemas.gate5 import ActivityReadiness, Gate5ReadinessOut, ReadinessItem
from app.services import audit
from app.services.position_coverage import role_position

SCOPES = {"PROCESS_OWNER", "ACCOUNTABLE", "EXECUTOR", "APPROVER", "BACKUP", "ESCALATION"}


def _process(db: Session, process_id: int) -> ProcessArch:
    row = db.get(ProcessArch, process_id)
    if row is None or row.level != 3 or row.is_draft:
        raise HTTPException(404, "责任闭合对象必须是正式 L3 流程")
    return row


def _published(db: Session, process: ProcessArch) -> Optional[ProcessModelVersion]:
    return db.scalar(
        select(ProcessModelVersion).where(
            ProcessModelVersion.process_id == process.id,
            ProcessModelVersion.version == process.published_model_version,
            ProcessModelVersion.status == "PUBLISHED",
        )
    )


def _item(code: str, message: str, severity: str = "BLOCKER") -> ReadinessItem:
    return ReadinessItem(code=code, message=message, severity=severity)


def _active_user(db: Session, user_id: Optional[int]) -> Optional[User]:
    user = db.get(User, user_id) if user_id else None
    return user if user and user.is_active else None


def _activities(db: Session, process: ProcessArch, version: ProcessModelVersion):
    nodes = {
        n["node_key"]: n for n in version.snapshot.get("nodes", []) if n.get("process_arch_id")
    }
    links = db.scalars(
        select(NodeActivityLink).where(
            NodeActivityLink.process_id == process.id,
            NodeActivityLink.model_version_id == version.id,
            NodeActivityLink.relation.in_({"REALIZES", "PART_OF"}),
        )
    ).all()
    mapped = {link.node_key: link.activity_id for link in links}
    for key, node in nodes.items():
        if key not in mapped and node.get("process_arch_id"):
            mapped[key] = node["process_arch_id"]
    return mapped, bool(links)


def readiness(db: Session, process_id: int, *, model_version_id: int | None = None, viewer=None):
    process = _process(db, process_id)
    version = (
        db.get(ProcessModelVersion, model_version_id)
        if model_version_id
        else _published(db, process)
    )
    blockers: list[ReadinessItem] = []
    warnings: list[ReadinessItem] = []
    if version is None or version.process_id != process.id:
        blockers.append(_item("NO_PUBLISHED_MODEL", "没有可核验的已发布模型"))
        return Gate5ReadinessOut(
            process_id=process.id,
            process_code=process.code,
            status="BLOCKED",
            evidence_grade="E0",
            process_owner={},
            blockers=blockers,
            configuration_writable=False,
        )
    if version.status != "PUBLISHED":
        warnings.append(
            _item("PREVIEW_MODEL", "当前为未发布模型预览，不产生正式责任证据", "WARNING")
        )
    if not process.owner_user_id:
        blockers.append(_item("OWNER_ACCOUNT_MISSING", "流程 Owner 未绑定真实账号"))
    elif _active_user(db, process.owner_user_id) is None:
        blockers.append(_item("OWNER_ACCOUNT_INVALID", "流程 Owner 账号不存在或已停用"))
    acceptance = db.scalar(
        select(ProcessResponsibilityAcceptance).where(
            ProcessResponsibilityAcceptance.process_id == process.id,
            ProcessResponsibilityAcceptance.model_version_id == version.id,
            ProcessResponsibilityAcceptance.node_key.is_(None),
            ProcessResponsibilityAcceptance.scope == "PROCESS_OWNER",
            ProcessResponsibilityAcceptance.status == "ACCEPTED",
        )
    )
    if acceptance is None:
        blockers.append(
            _item("OWNER_ACCEPTANCE_MISSING", "流程 Owner 缺少当前模型版本的责任接受记录")
        )
    mapped, has_versioned_links = _activities(db, process, version)
    if not has_versioned_links:
        warnings.append(
            _item(
                "LEGACY_ACTIVITY_MAPPING",
                "当前模型没有版本化活动映射，仅使用兼容主活动指针",
                "WARNING",
            )
        )
    activity_rows = {
        a.id: a
        for a in db.scalars(
            select(ProcessArch).where(ProcessArch.id.in_(set(mapped.values())))
        ).all()
    }
    activity_results = []
    for node_key, activity_id in sorted(mapped.items()):
        activity_blockers: list[ReadinessItem] = []
        activity_warnings: list[ReadinessItem] = []
        activity = activity_rows.get(activity_id)
        if activity is None or activity.level != 4 or activity.parent_id != process.id:
            activity_blockers.append(_item("ACTIVITY_MAPPING_INVALID", "活动映射无效"))
        raci = db.scalars(
            select(RaciAssignment).where(
                RaciAssignment.process_id == process.id,
                RaciAssignment.activity_id == activity_id,
                RaciAssignment.raci == "A",
            )
        ).all()
        if len(raci) != 1:
            activity_blockers.append(_item("ACTIVITY_A_NOT_UNIQUE", "活动必须有且只有一个活动级 A"))
        elif not role_position(db, db.get(GovernanceRole, raci[0].role_id)):
            activity_blockers.append(
                _item("ACCOUNTABLE_ROLE_INVALID", "A 对应治理角色成员或岗位无效")
            )
        assignment = db.scalar(
            select(NodeAssignment).where(
                NodeAssignment.process_id == process.id,
                NodeAssignment.node_key == node_key,
                NodeAssignment.is_active.is_(True),
                or_(
                    NodeAssignment.model_version_id == version.id,
                    NodeAssignment.model_version_id.is_(None),
                ),
            )
        )
        if assignment is None:
            activity_blockers.append(_item("NODE_ASSIGNMENT_MISSING", "缺少节点责任配置"))
        else:
            if assignment.model_version_id is None:
                activity_warnings.append(
                    _item("ASSIGNMENT_UNVERSIONED", "节点责任配置未绑定模型版本", "WARNING")
                )
            if _active_user(db, assignment.default_assignee_user_id) is None:
                activity_blockers.append(_item("EXECUTOR_MISSING", "缺少有效默认执行账号"))
            if _active_user(db, assignment.approver_user_id) is None:
                activity_blockers.append(_item("APPROVER_MISSING", "缺少有效审批账号"))
            if (
                assignment.default_assignee_user_id
                and assignment.default_assignee_user_id == assignment.approver_user_id
            ):
                activity_blockers.append(
                    _item("APPROVAL_SELF_CONFLICT", "执行账号与审批账号不能相同")
                )
            if _active_user(db, assignment.backup_assignee_user_id) is None:
                activity_blockers.append(_item("BACKUP_MISSING", "缺少有效备用责任人"))
            if _active_user(db, assignment.escalation_user_id) is None:
                activity_blockers.append(_item("ESCALATION_MISSING", "缺少有效升级责任人"))
        for scope, code, message in (
            ("ACCOUNTABLE", "ACCOUNTABILITY_ACCEPTANCE_MISSING", "A 缺少责任接受"),
            ("EXECUTOR", "EXECUTOR_ACCEPTANCE_MISSING", "执行人缺少责任接受"),
            ("BACKUP", "BACKUP_ACCEPTANCE_MISSING", "备用责任人缺少责任接受"),
            ("ESCALATION", "ESCALATION_ACCEPTANCE_MISSING", "升级责任人缺少责任接受"),
        ):
            if not db.scalar(
                select(ProcessResponsibilityAcceptance.id).where(
                    ProcessResponsibilityAcceptance.process_id == process.id,
                    ProcessResponsibilityAcceptance.model_version_id == version.id,
                    ProcessResponsibilityAcceptance.node_key == node_key,
                    ProcessResponsibilityAcceptance.scope == scope,
                    ProcessResponsibilityAcceptance.status == "ACCEPTED",
                )
            ):
                activity_blockers.append(_item(code, message))
        activity_results.append(
            ActivityReadiness(
                node_key=node_key,
                activity_id=activity_id,
                activity_code=activity.code if activity else None,
                status="PASS" if not activity_blockers else "BLOCKED",
                evidence_grade="E2" if not activity_blockers else "E1",
                blockers=activity_blockers,
                warnings=activity_warnings,
            )
        )
    blockers.extend(item for row in activity_results for item in row.blockers)
    warnings.extend(item for row in activity_results for item in row.warnings)
    status = "PASS" if not blockers and version.status == "PUBLISHED" else "BLOCKED"
    return Gate5ReadinessOut(
        process_id=process.id,
        process_code=process.code,
        model_version_id=version.id,
        model_version=version.version,
        status=status,
        evidence_grade="E2" if status == "PASS" else "E1",
        process_owner={"user_id": process.owner_user_id, "label": process.owner or None},
        activities=activity_results,
        blockers=blockers,
        warnings=warnings,
        next_actions=[item.message for item in blockers[:10]],
        configuration_writable=viewer is not None and viewer.role in {"ADMIN", "MANAGER"},
        business_accepted=status == "PASS",
    )


def _write_user(actor):
    if actor is None or actor.role not in {"ADMIN", "MANAGER", "OWNER"}:
        raise HTTPException(403, "没有责任配置写权限")


def set_process_owner(
    db: Session,
    process: ProcessArch,
    *,
    owner_user_id: int,
    actor: User,
    expected_model_version_id: int,
):
    _write_user(actor)
    version = _published(db, process)
    if version is None or version.id != expected_model_version_id:
        raise HTTPException(409, "已发布模型版本已变化，请刷新")
    if _active_user(db, owner_user_id) is None:
        raise HTTPException(400, "Owner 账号不存在或已停用")
    process.owner_user_id = owner_user_id
    audit.record(
        db, actor, "UPDATE", "process_owner", process.id, f"绑定流程 Owner 用户 {owner_user_id}"
    )
    return process


def upsert_assignment(
    db: Session,
    process: ProcessArch,
    node_key: str,
    values: dict,
    actor: User,
    expected_model_version_id: int,
):
    _write_user(actor)
    version = _published(db, process)
    if version is None or version.id != expected_model_version_id:
        raise HTTPException(409, "已发布模型版本已变化，请刷新")
    if not any(n.get("node_key") == node_key for n in version.snapshot.get("nodes", [])):
        raise HTTPException(404, "节点不属于当前发布模型")
    for key in (
        "default_assignee_user_id",
        "approver_user_id",
        "backup_assignee_user_id",
        "escalation_user_id",
    ):
        if values.get(key) is not None and _active_user(db, values[key]) is None:
            raise HTTPException(400, f"{key} 指向的用户不存在或已停用")
    if values.get("default_assignee_user_id") == values.get("approver_user_id") and values.get(
        "default_assignee_user_id"
    ):
        raise HTTPException(400, "执行账号与审批账号不能相同")
    row = db.scalar(
        select(NodeAssignment).where(
            NodeAssignment.process_id == process.id, NodeAssignment.node_key == node_key
        )
    )
    if row is None:
        row = NodeAssignment(process_id=process.id, node_key=node_key)
        db.add(row)
    for key, value in values.items():
        setattr(row, key, value)
    row.model_version_id = version.id
    db.flush()
    audit.record(
        db,
        actor,
        "UPDATE",
        "node_assignment",
        row.id,
        f"写入 {process.code}/{node_key} Gate 5 责任配置",
    )
    return row


def accept_responsibility(
    db: Session,
    process: ProcessArch,
    *,
    model_version_id: int,
    node_key: Optional[str],
    scope: str,
    subject_user_id: int,
    actor: User,
    valid_until: Optional[date],
    evidence_note: Optional[str],
):
    _write_user(actor)
    version = _published(db, process)
    if version is None or version.id != model_version_id:
        raise HTTPException(409, "只允许对当前已发布模型写入责任接受")
    if scope not in SCOPES or _active_user(db, subject_user_id) is None:
        raise HTTPException(400, "责任范围或责任账号无效")
    if actor.id != subject_user_id and actor.role not in {"ADMIN", "MANAGER"}:
        raise HTTPException(403, "只能由责任人本人或治理管理员确认")
    existing = db.scalar(
        select(ProcessResponsibilityAcceptance).where(
            ProcessResponsibilityAcceptance.process_id == process.id,
            ProcessResponsibilityAcceptance.model_version_id == model_version_id,
            ProcessResponsibilityAcceptance.node_key == node_key,
            ProcessResponsibilityAcceptance.scope == scope,
            ProcessResponsibilityAcceptance.subject_user_id == subject_user_id,
            ProcessResponsibilityAcceptance.status == "ACCEPTED",
        )
    )
    if existing is not None:
        raise HTTPException(409, "当前模型版本已有有效的责任接受记录")
    row = ProcessResponsibilityAcceptance(
        process_id=process.id,
        model_version_id=model_version_id,
        node_key=node_key,
        scope=scope,
        subject_user_id=subject_user_id,
        accepted_by_user_id=actor.id,
        accepted_at=utcnow(),
        valid_until=valid_until,
        evidence_note=evidence_note,
        status="ACCEPTED",
    )
    db.add(row)
    db.flush()
    audit.record(
        db, actor, "CREATE", "responsibility_acceptance", row.id, f"确认 {process.code} {scope}"
    )
    return row
