"""步骤契约与交付物服务：实例化、版本状态机、恢复指针。

版本规则的唯一实现放在这里：API 层只做鉴权和入参校验，不自己判断状态流转。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
    StepContract,
)
from app.models.enums import DeliverableStatus, DeliverableType, ToolLevel
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project, ProjectStep, WorkflowTemplate
from app.models.tool import Tool
from app.models.user import User
from app.schemas.deliverable import (
    DeliverableDefinitionOut,
    DeliverableInstanceDetail,
    DeliverableInstanceOut,
    DeliverableSummary,
    DeliverableVersionOut,
    StepContractOut,
    ToolRefOut,
)
from app.services import process_scope

TYPE_LABELS: Dict[str, str] = {
    DeliverableType.DOCUMENT.value: "文档",
    DeliverableType.FORM.value: "表单",
    DeliverableType.DIAGRAM.value: "图表",
    DeliverableType.REPORT.value: "报告",
    DeliverableType.DATA.value: "清单/台账",
    DeliverableType.DECISION.value: "决策记录",
}

STATUS_LABELS: Dict[str, str] = {
    DeliverableStatus.MISSING.value: "未产出",
    DeliverableStatus.DRAFT.value: "草稿",
    DeliverableStatus.IN_REVIEW.value: "评审中",
    DeliverableStatus.APPROVED.value: "已批准",
    DeliverableStatus.EFFECTIVE.value: "已生效",
    DeliverableStatus.SUPERSEDED.value: "已被替代",
    DeliverableStatus.RETIRED.value: "已作废",
}

TOOL_CATEGORY_LABELS: Dict[str, str] = {
    "DIAGNOSE": "诊断工具",
    "DESIGN": "设计工具",
    "DEPLOY": "落地工具",
    "MONITOR": "监控工具",
}

TOOL_LEVEL_LABELS: Dict[str, str] = {
    ToolLevel.REQUIRED.value: "必用",
    ToolLevel.RECOMMENDED.value: "推荐",
    ToolLevel.OPTIONAL.value: "可选",
}

# 版本状态机：只允许向前审批，或退回草稿；作废是终态。
ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    DeliverableStatus.DRAFT.value: [
        DeliverableStatus.IN_REVIEW.value,
        DeliverableStatus.RETIRED.value,
    ],
    DeliverableStatus.IN_REVIEW.value: [
        DeliverableStatus.APPROVED.value,
        DeliverableStatus.DRAFT.value,
        DeliverableStatus.RETIRED.value,
    ],
    DeliverableStatus.APPROVED.value: [
        DeliverableStatus.EFFECTIVE.value,
        DeliverableStatus.DRAFT.value,
        DeliverableStatus.RETIRED.value,
    ],
    DeliverableStatus.EFFECTIVE.value: [
        DeliverableStatus.SUPERSEDED.value,
        DeliverableStatus.RETIRED.value,
    ],
    DeliverableStatus.SUPERSEDED.value: [DeliverableStatus.RETIRED.value],
    DeliverableStatus.RETIRED.value: [],
}

# 恢复旧版只对「已批准过」的版本开放；草稿没有被批准过，不构成可恢复的历史。
_RESTORABLE = {
    DeliverableStatus.APPROVED.value,
    DeliverableStatus.EFFECTIVE.value,
    DeliverableStatus.SUPERSEDED.value,
}


class DeliverableError(ValueError):
    """业务规则拒绝；API 层转成 400/409。"""


# ------------------------------------------------------------------ 步骤契约


def require_step(db: Session, step_no: str) -> WorkflowTemplate:
    step = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.step_no == step_no))
    if step is None:
        raise DeliverableError(f"标准步骤 {step_no} 不存在")
    return step


def resolve_tool_codes(db: Session, codes: Sequence[str]) -> List[str]:
    """校验并去重工具编码，保持传入顺序。"""
    ordered: List[str] = []
    for code in codes:
        if code not in ordered:
            ordered.append(code)
    if not ordered:
        return []
    known = set(db.scalars(select(Tool.code).where(Tool.code.in_(ordered))).all())
    unknown = [code for code in ordered if code not in known]
    if unknown:
        raise DeliverableError(f"工具编码不存在：{', '.join(unknown)}")
    return ordered


def default_tool_levels(codes: Sequence[str]) -> Dict[str, str]:
    """没有显式配置时的兜底：第一个工具视作必用，其余推荐。"""
    return {
        code: (ToolLevel.REQUIRED.value if index == 0 else ToolLevel.RECOMMENDED.value)
        for index, code in enumerate(codes)
    }


def normalized_tool_levels(codes: Sequence[str], raw: Optional[dict]) -> Dict[str, str]:
    levels = default_tool_levels(codes)
    for code, level in (raw or {}).items():
        value = level.value if isinstance(level, ToolLevel) else str(level)
        if code in levels and value in TOOL_LEVEL_LABELS:
            levels[code] = value
    return levels


def get_contract(db: Session, step_no: str) -> StepContractOut:
    step = require_step(db, step_no)
    contract = db.scalar(select(StepContract).where(StepContract.step_no == step_no))
    codes = list(contract.tool_codes or []) if contract else []
    levels = normalized_tool_levels(codes, contract.tool_levels if contract else None)
    tools = _tool_refs(db, codes, levels)
    definitions = _definitions_out(db, step_no)
    return StepContractOut(
        step_no=step.step_no,
        step_name=step.name,
        stage_no=step.stage_no,
        inputs=contract.inputs if contract else None,
        tool_codes=codes,
        tool_levels=levels,
        tools=tools,
        acceptance_criteria=contract.acceptance_criteria if contract else None,
        owner_role=contract.owner_role if contract else None,
        decision_gate=bool(contract.decision_gate) if contract else False,
        deliverables=definitions,
        updated_at=contract.updated_at if contract else None,
    )


def save_contract(db: Session, step_no: str, payload: dict, user: User) -> StepContract:
    require_step(db, step_no)
    contract = db.scalar(select(StepContract).where(StepContract.step_no == step_no))
    if contract is None:
        contract = StepContract(step_no=step_no, tool_codes=[])
        db.add(contract)
        db.flush()
    if "tool_codes" in payload:
        codes = resolve_tool_codes(db, payload["tool_codes"] or [])
        contract.tool_codes = codes
        # 新增/删除工具后，使用要求跟着收缩回合法集合
        contract.tool_levels = normalized_tool_levels(codes, contract.tool_levels)
    if "tool_levels" in payload:
        codes = list(contract.tool_codes or [])
        raw = payload["tool_levels"] or {}
        unknown = [code for code in raw if code not in codes]
        if unknown:
            raise DeliverableError(
                f"tool_levels 里的工具不在本步骤工具清单中：{', '.join(unknown)}"
            )
        for level in raw.values():
            if (
                level.value if isinstance(level, ToolLevel) else str(level)
            ) not in TOOL_LEVEL_LABELS:
                raise DeliverableError(f"未知的工具使用要求：{level}")
        contract.tool_levels = normalized_tool_levels(codes, raw)
    for field in ("inputs", "acceptance_criteria", "owner_role"):
        if field in payload:
            setattr(contract, field, payload[field])
    if payload.get("decision_gate") is not None:
        contract.decision_gate = payload["decision_gate"]
    db.flush()
    return contract


def _tool_refs(
    db: Session, codes: Sequence[str], levels: Optional[dict] = None
) -> List[ToolRefOut]:
    if not codes:
        return []
    levels = levels or default_tool_levels(codes)
    rows = {t.code: t for t in db.scalars(select(Tool).where(Tool.code.in_(codes))).all()}
    return [
        ToolRefOut(
            code=t.code,
            name=t.name,
            category=t.category,
            category_label=TOOL_CATEGORY_LABELS.get(t.category, t.category),
            stage_no=t.stage_no,
            level=levels.get(code, ToolLevel.RECOMMENDED.value),
            level_label=TOOL_LEVEL_LABELS.get(
                levels.get(code, ToolLevel.RECOMMENDED.value),
                levels.get(code, ToolLevel.RECOMMENDED.value),
            ),
        )
        for code in codes
        if (t := rows.get(code)) is not None
    ]


def definition_out(definition: DeliverableDefinition) -> DeliverableDefinitionOut:
    return DeliverableDefinitionOut(
        id=definition.id,
        code=definition.code,
        name=definition.name,
        step_no=definition.step_no,
        type=definition.type,
        type_label=TYPE_LABELS.get(definition.type, definition.type),
        required=definition.required,
        template_ref=definition.template_ref,
        acceptance_criteria=definition.acceptance_criteria,
        sort_order=definition.sort_order,
        is_active=definition.is_active,
    )


def _definitions_out(db: Session, step_no: str) -> List[DeliverableDefinitionOut]:
    rows = db.scalars(
        select(DeliverableDefinition)
        .where(DeliverableDefinition.step_no == step_no)
        .order_by(DeliverableDefinition.sort_order, DeliverableDefinition.id)
    ).all()
    return [definition_out(row) for row in rows]


def next_definition_code(db: Session, step_no: str) -> str:
    prefix = f"DLV-{step_no}-"
    existing = db.scalars(
        select(DeliverableDefinition.code).where(DeliverableDefinition.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:02d}"


# ------------------------------------------------------------------ 实例化


def sync_project_instances(db: Session, project: Project) -> int:
    """按当前生效的交付物定义为项目的每个步骤补齐实例，幂等。

    定义在项目立项后新增时，调用方（同步接口）也能把缺的实例补上。
    """
    steps = db.scalars(select(ProjectStep).where(ProjectStep.project_id == project.id)).all()
    step_by_no = {step.step_no: step for step in steps}
    existing = set(
        db.execute(
            select(DeliverableInstance.project_step_id, DeliverableInstance.definition_id).where(
                DeliverableInstance.project_id == project.id
            )
        ).all()
    )
    definitions = db.scalars(
        select(DeliverableDefinition).where(DeliverableDefinition.is_active.is_(True))
    ).all()
    created = 0
    for definition in definitions:
        step = step_by_no.get(definition.step_no)
        if step is None or (step.id, definition.id) in existing:
            continue
        db.add(
            DeliverableInstance(
                definition_id=definition.id,
                project_id=project.id,
                project_step_id=step.id,
                status=DeliverableStatus.MISSING.value,
                owner=step.owner,
            )
        )
        created += 1
    db.flush()
    return created


# ------------------------------------------------------------------ 版本


def _validate_source_document(db: Session, instance: DeliverableInstance, version_id: int) -> None:
    version = db.get(ProcessDocumentVersion, version_id)
    if version is None:
        raise DeliverableError("来源流程标准版本不存在")
    if version.status != DeliverableStatus.EFFECTIVE.value:
        raise DeliverableError("只能引用已生效的流程标准版本")
    document = db.get(ProcessDocument, version.document_id)
    if document is None:
        raise DeliverableError("来源流程标准文档不存在")
    project = db.get(Project, instance.project_id)
    if project is not None and not process_scope.is_document_applicable(
        db, document.process_id, project.process_id
    ):
        raise DeliverableError("该标准文件不属于本项目流程或其上级流程")


def create_version(
    db: Session,
    instance: DeliverableInstance,
    payload: dict,
    user: User,
) -> DeliverableVersion:
    last_no = (
        db.scalar(
            select(func.max(DeliverableVersion.version_no)).where(
                DeliverableVersion.instance_id == instance.id
            )
        )
        or 0
    )
    base_id = payload.get("base_version_id") or instance.current_version_id
    if base_id is not None:
        base = db.get(DeliverableVersion, base_id)
        if base is None or base.instance_id != instance.id:
            raise DeliverableError("base_version_id 不属于该交付物")
    source_document_version_id = payload.get("source_document_version_id")
    if source_document_version_id is not None:
        _validate_source_document(db, instance, source_document_version_id)
    version = DeliverableVersion(
        instance_id=instance.id,
        version_no=last_no + 1,
        status=DeliverableStatus.DRAFT.value,
        author=user.display_name,
        author_id=user.id,
        base_version_id=base_id,
    )
    for field in (
        "title",
        "note",
        "file_ref",
        "file_name",
        "mime_type",
        "size_bytes",
        "checksum",
        "storage_backend",
        "storage_key",
        "source_template_version_id",
        "source_document_version_id",
        "valid_from",
    ):
        if field in payload and payload[field] is not None:
            setattr(version, field, payload[field])
    db.add(version)
    db.flush()
    instance.current_version_id = version.id
    _sync_instance_status(db, instance)
    db.flush()
    return version


def transition_version(
    db: Session,
    instance: DeliverableInstance,
    version: DeliverableVersion,
    target: str,
    user: User,
    note: Optional[str] = None,
) -> DeliverableVersion:
    current = version.status
    allowed = ALLOWED_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise DeliverableError(
            f"不允许从 {STATUS_LABELS.get(current, current)} 变更为 {STATUS_LABELS.get(target, target)}"
        )

    today = date.today()
    if target == DeliverableStatus.APPROVED.value:
        version.approver = user.display_name
        version.approver_id = user.id
        version.approved_at = utcnow()
        if version.valid_from is None:
            version.valid_from = today
    elif target == DeliverableStatus.EFFECTIVE.value:
        _supersede_others(db, instance, version, today)
        if version.valid_from is None:
            version.valid_from = today
        version.valid_to = None
    elif target == DeliverableStatus.SUPERSEDED.value:
        version.valid_to = today
    elif target == DeliverableStatus.RETIRED.value:
        version.valid_to = today
    elif target == DeliverableStatus.DRAFT.value:
        # 退回草稿：清掉批准记录，避免留下「批准过」的假象
        version.approver = None
        version.approver_id = None
        version.approved_at = None
        version.valid_from = None

    version.status = target
    if target == DeliverableStatus.EFFECTIVE.value:
        # 生效版就是当前版：即使操作的是旧版本，指针也要跟过来
        instance.current_version_id = version.id
    elif target == DeliverableStatus.RETIRED.value and instance.current_version_id == version.id:
        _move_pointer_if_retired(db, instance, version)
    _sync_instance_status(db, instance)
    db.flush()
    return version


def restore_version(
    db: Session,
    instance: DeliverableInstance,
    version: DeliverableVersion,
    user: User,
) -> DeliverableVersion:
    """恢复旧版 = 移动当前版本指针，不复制文件。"""
    if version.instance_id != instance.id:
        raise DeliverableError("版本不属于该交付物")
    if version.status not in _RESTORABLE:
        raise DeliverableError("只有已批准的版本才能恢复为现行版")
    today = date.today()
    _supersede_others(db, instance, version, today)
    version.status = DeliverableStatus.EFFECTIVE.value
    version.valid_to = None
    if version.valid_from is None:
        version.valid_from = today
    instance.current_version_id = version.id
    _sync_instance_status(db, instance)
    db.flush()
    return version


def _sync_instance_status(db: Session, instance: DeliverableInstance) -> None:
    """实例状态只在一处推导。

    只要还有生效版本，交付物就是「已生效」——正在起草的 R2 不会把 R1 的生效状态
    拉回草稿；没有生效版本时才跟随当前指针。
    """
    db.flush()
    has_effective = (
        db.scalar(
            select(func.count())
            .select_from(DeliverableVersion)
            .where(
                DeliverableVersion.instance_id == instance.id,
                DeliverableVersion.status == DeliverableStatus.EFFECTIVE.value,
            )
        )
        or 0
    )
    if has_effective:
        instance.status = DeliverableStatus.EFFECTIVE.value
        return
    current = (
        db.get(DeliverableVersion, instance.current_version_id)
        if instance.current_version_id
        else None
    )
    instance.status = current.status if current else DeliverableStatus.MISSING.value


def _supersede_others(
    db: Session,
    instance: DeliverableInstance,
    keep: DeliverableVersion,
    today: date,
) -> None:
    others = db.scalars(
        select(DeliverableVersion).where(
            DeliverableVersion.instance_id == instance.id,
            DeliverableVersion.id != keep.id,
            DeliverableVersion.status == DeliverableStatus.EFFECTIVE.value,
        )
    ).all()
    for other in others:
        other.status = DeliverableStatus.SUPERSEDED.value
        other.valid_to = today


def _move_pointer_if_retired(
    db: Session, instance: DeliverableInstance, retired: DeliverableVersion
) -> None:
    if instance.current_version_id != retired.id:
        return
    replacement = db.scalar(
        select(DeliverableVersion)
        .where(
            DeliverableVersion.instance_id == instance.id,
            DeliverableVersion.id != retired.id,
            DeliverableVersion.status != DeliverableStatus.RETIRED.value,
        )
        .order_by(DeliverableVersion.version_no.desc())
        .limit(1)
    )
    instance.current_version_id = replacement.id if replacement else None


# ------------------------------------------------------------------ 出参


def version_out(version: DeliverableVersion) -> DeliverableVersionOut:
    has_file = bool(version.storage_key)
    return DeliverableVersionOut(
        id=version.id,
        instance_id=version.instance_id,
        version_no=version.version_no,
        version_label=f"R{version.version_no}",
        status=version.status,
        status_label=STATUS_LABELS.get(version.status, version.status),
        title=version.title,
        note=version.note,
        file_ref=version.file_ref,
        file_name=version.file_name,
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        checksum=version.checksum,
        storage_backend=version.storage_backend,
        has_file=has_file,
        download_url=(
            f"{settings.api_prefix}/deliverables/{version.instance_id}/versions/{version.id}/download"
            if has_file
            else None
        ),
        author=version.author,
        reviewer=version.reviewer,
        approver=version.approver,
        approved_at=version.approved_at,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        base_version_id=version.base_version_id,
        source_template_version_id=version.source_template_version_id,
        source_document_version_id=version.source_document_version_id,
        source_document_label=(
            f"{version.source_document_version.document.code} "
            f"v{version.source_document_version.version_label}"
            if version.source_document_version and version.source_document_version.document
            else None
        ),
        created_at=version.created_at,
    )


def instance_out(
    instance: DeliverableInstance,
    versions: Optional[List[DeliverableVersion]] = None,
) -> DeliverableInstanceOut:
    definition = instance.definition
    step = instance.step
    all_versions = versions if versions is not None else list(instance.versions)
    current = next(
        (v for v in all_versions if v.id == instance.current_version_id),
        None,
    )
    return DeliverableInstanceOut(
        id=instance.id,
        project_id=instance.project_id,
        project_code=instance.project.code if instance.project else None,
        process_id=instance.project.process_id if instance.project else None,
        project_step_id=instance.project_step_id,
        step_no=step.step_no,
        step_name=step.name,
        definition_id=definition.id,
        definition_code=definition.code,
        definition_name=definition.name,
        type=definition.type,
        type_label=TYPE_LABELS.get(definition.type, definition.type),
        required=definition.required,
        acceptance_criteria=definition.acceptance_criteria,
        status=instance.status,
        status_label=STATUS_LABELS.get(instance.status, instance.status),
        owner=instance.owner,
        owner_user_id=instance.owner_user_id,
        current_version_id=instance.current_version_id,
        current_version=version_out(current) if current else None,
        version_count=len(all_versions),
        updated_at=instance.updated_at,
    )


def instance_detail(db: Session, instance: DeliverableInstance) -> DeliverableInstanceDetail:
    versions = db.scalars(
        select(DeliverableVersion)
        .where(DeliverableVersion.instance_id == instance.id)
        .order_by(DeliverableVersion.version_no)
    ).all()
    base = instance_out(instance, list(versions))
    return DeliverableInstanceDetail(
        **base.model_dump(),
        versions=[version_out(v) for v in versions],
    )


def project_instances(db: Session, project_id: int) -> List[DeliverableInstance]:
    return list(
        db.scalars(
            select(DeliverableInstance)
            .where(DeliverableInstance.project_id == project_id)
            .order_by(DeliverableInstance.project_step_id, DeliverableInstance.id)
        ).all()
    )


def project_summary(db: Session, project_id: int) -> DeliverableSummary:
    rows: List[Tuple[str, int, bool]] = db.execute(
        select(
            DeliverableInstance.status,
            func.count(DeliverableInstance.id),
            DeliverableDefinition.required,
        )
        .join(DeliverableDefinition, DeliverableDefinition.id == DeliverableInstance.definition_id)
        .where(DeliverableInstance.project_id == project_id)
        .group_by(DeliverableInstance.status, DeliverableDefinition.required)
    ).all()

    by_status: Dict[str, int] = {}
    total = required_total = required_missing = 0
    for status, count, required in rows:
        by_status[status] = by_status.get(status, 0) + count
        total += count
        if required:
            required_total += count
            if status == DeliverableStatus.MISSING.value:
                required_missing += count
    effective = by_status.get(DeliverableStatus.EFFECTIVE.value, 0)
    return DeliverableSummary(
        total=total,
        required_total=required_total,
        effective=effective,
        in_review=by_status.get(DeliverableStatus.IN_REVIEW.value, 0),
        draft=by_status.get(DeliverableStatus.DRAFT.value, 0),
        missing=by_status.get(DeliverableStatus.MISSING.value, 0),
        required_missing=required_missing,
        completeness_pct=round(effective / total * 100, 1) if total else 0.0,
        by_status=by_status,
        status_labels=STATUS_LABELS,
    )
