"""工具预制模板服务：模板库、版本状态机、调用记录、复制到项目。

版本状态机与交付物共用 `deliverable.ALLOWED_TRANSITIONS`，不另造一套审批规则；
模板版本的文件复用 `storage.py`，复制到项目时真正复制一份，保证模板升级不影响已复制实例。
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
    StepContract,
)
from app.models.enums import DeliverableStatus, TemplateFormat, TemplateMode, ToolLevel
from app.models.process import ProcessArch
from app.models.project import Project, WorkflowTemplate
from app.models.tool import Tool
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.models.user import User
from app.schemas.deliverable import RecommendedToolOut, StepRecommendationOut
from app.schemas.tool_template import (
    PlaceholderValue,
    TemplateContext,
    TemplateMeta,
    TemplateUsageOut,
    ToolTemplateDetail,
    ToolTemplateOut,
    ToolTemplateVersionOut,
)
from app.services import deliverable as deliverable_service
from app.services import org_unit as org_service
from app.services import storage as storage_service

FORMAT_LABELS: Dict[str, str] = {
    TemplateFormat.XLSX.value: "Excel",
    TemplateFormat.DOCX.value: "Word",
    TemplateFormat.PPTX.value: "PowerPoint",
    TemplateFormat.BPMN.value: "BPMN",
    TemplateFormat.ONLINE.value: "在线模板",
    TemplateFormat.PDF.value: "PDF",
    TemplateFormat.CSV.value: "CSV",
}

MODE_LABELS: Dict[str, str] = {
    TemplateMode.DOWNLOAD.value: "下载副本",
    TemplateMode.ONLINE.value: "在线填写",
    TemplateMode.GENERATE.value: "服务端生成",
    TemplateMode.LINK.value: "引用查看",
}

# 每种格式允许的文件扩展名；ONLINE 不带文件
FORMAT_EXTENSIONS: Dict[str, Tuple[str, ...]] = {
    TemplateFormat.XLSX.value: (".xlsx", ".xlsm"),
    TemplateFormat.DOCX.value: (".docx",),
    TemplateFormat.PPTX.value: (".pptx",),
    TemplateFormat.PDF.value: (".pdf",),
    TemplateFormat.BPMN.value: (".bpmn", ".xml"),
    TemplateFormat.CSV.value: (".csv",),
    TemplateFormat.ONLINE.value: (),
}

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


class TemplateError(ValueError):
    """模板业务规则拒绝；API 层转成 400/409。"""


# ------------------------------------------------------------------ 模板


def require_tool(db: Session, code: str) -> Tool:
    tool = db.scalar(select(Tool).where(Tool.code == code))
    if tool is None:
        raise TemplateError(f"工具 {code} 不存在")
    return tool


def require_template(db: Session, template_id: int) -> ToolTemplate:
    template = db.get(ToolTemplate, template_id)
    if template is None:
        raise TemplateError(f"模板 {template_id} 不存在")
    return template


def next_template_code(db: Session, tool_code: str) -> str:
    prefix = f"TPL-{tool_code}-"
    existing = db.scalars(
        select(ToolTemplate.code).where(ToolTemplate.code.like(f"{prefix}%"))
    ).all()
    seq = 0
    for code in existing:
        try:
            seq = max(seq, int(code.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"{prefix}{seq + 1:02d}"


def create_template(db: Session, data: dict) -> ToolTemplate:
    require_tool(db, data["tool_code"])
    template = ToolTemplate(**data)
    db.add(template)
    db.flush()
    return template


def set_default(db: Session, template: ToolTemplate) -> None:
    """同一工具 + 同一格式只保留一个默认模板。"""
    others = db.scalars(
        select(ToolTemplate).where(
            ToolTemplate.id != template.id,
            ToolTemplate.tool_code == template.tool_code,
            ToolTemplate.format == template.format,
            ToolTemplate.is_default.is_(True),
        )
    ).all()
    for other in others:
        other.is_default = False
    template.is_default = True


def ensure_default(db: Session, tool_code: str, template_format: str) -> None:
    """没有默认模板时自动从同工具同格式的启用模板里选一个，避免库里出现「无默认」。"""
    exists = db.scalar(
        select(ToolTemplate.id)
        .where(
            ToolTemplate.tool_code == tool_code,
            ToolTemplate.format == template_format,
            ToolTemplate.is_default.is_(True),
            ToolTemplate.is_active.is_(True),
        )
        .limit(1)
    )
    if exists is not None:
        return
    candidate = db.scalar(
        select(ToolTemplate)
        .where(
            ToolTemplate.tool_code == tool_code,
            ToolTemplate.format == template_format,
            ToolTemplate.is_active.is_(True),
        )
        .order_by(ToolTemplate.id)
        .limit(1)
    )
    if candidate is not None:
        candidate.is_default = True


def version_label_in_use(db: Session, template_id: int, label: str) -> bool:
    return (
        db.scalar(
            select(func.count())
            .select_from(ToolTemplateVersion)
            .where(
                ToolTemplateVersion.template_id == template_id,
                ToolTemplateVersion.version_label == label,
            )
        )
        or 0
    ) > 0


def format_accepts(filename: str, template_format: str) -> bool:
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return f".{suffix}" in FORMAT_EXTENSIONS.get(template_format, ())


# ------------------------------------------------------------------ 版本


def create_version(
    db: Session,
    template: ToolTemplate,
    data: dict,
    user: User,
    file_meta: Optional[dict] = None,
) -> ToolTemplateVersion:
    label = data["version_label"]
    if not _VERSION_RE.match(label):
        raise TemplateError("版本号必须形如 major.minor.patch，例如 1.0.0")
    if version_label_in_use(db, template.id, label):
        raise TemplateError(f"版本 {label} 已存在，版本只追加不覆盖")

    base_id = data.get("base_version_id") or template.current_version_id
    if base_id is not None:
        base = db.get(ToolTemplateVersion, base_id)
        if base is None or base.template_id != template.id:
            raise TemplateError("base_version_id 不属于该模板")

    version = ToolTemplateVersion(
        template_id=template.id,
        version_label=label,
        status=DeliverableStatus.DRAFT.value,
        note=data.get("note"),
        valid_from=data.get("valid_from"),
        base_version_id=base_id,
        placeholders=[_placeholder_dict(p) for p in data.get("placeholders") or []],
        created_by=user.display_name,
        created_by_id=user.id,
    )
    if file_meta:
        for field in (
            "file_name",
            "mime_type",
            "size_bytes",
            "checksum",
            "storage_backend",
            "storage_key",
        ):
            setattr(version, field, file_meta.get(field))
    db.add(version)
    db.flush()
    template.current_version_id = version.id
    db.flush()
    return version


def _placeholder_dict(spec: Any) -> dict:
    if isinstance(spec, dict):
        return dict(spec)
    return spec.model_dump()


def transition_version(
    db: Session,
    template: ToolTemplate,
    version: ToolTemplateVersion,
    target: str,
    user: User,
    note: Optional[str] = None,
) -> ToolTemplateVersion:
    allowed = deliverable_service.ALLOWED_TRANSITIONS.get(version.status, [])
    if target not in allowed:
        raise TemplateError(
            f"不允许从 {deliverable_service.STATUS_LABELS.get(version.status, version.status)} "
            f"变更为 {deliverable_service.STATUS_LABELS.get(target, target)}"
        )

    today = date.today()
    if target == DeliverableStatus.APPROVED.value:
        version.approved_by = user.display_name
        version.approved_by_id = user.id
        version.approved_at = utcnow()
        if version.valid_from is None:
            version.valid_from = today
    elif target == DeliverableStatus.EFFECTIVE.value:
        _supersede_others(db, template, version, today)
        version.valid_to = None
        if version.valid_from is None:
            version.valid_from = today
        template.current_version_id = version.id
    elif target in {DeliverableStatus.SUPERSEDED.value, DeliverableStatus.RETIRED.value}:
        version.valid_to = today
    elif target == DeliverableStatus.DRAFT.value:
        version.approved_by = None
        version.approved_by_id = None
        version.approved_at = None
        version.valid_from = None

    version.status = target
    db.flush()
    return version


def _supersede_others(
    db: Session, template: ToolTemplate, keep: ToolTemplateVersion, today: date
) -> None:
    others = db.scalars(
        select(ToolTemplateVersion).where(
            ToolTemplateVersion.template_id == template.id,
            ToolTemplateVersion.id != keep.id,
            ToolTemplateVersion.status == DeliverableStatus.EFFECTIVE.value,
        )
    ).all()
    for other in others:
        other.status = DeliverableStatus.SUPERSEDED.value
        other.valid_to = today


def effective_version(template: ToolTemplate) -> Optional[ToolTemplateVersion]:
    """当前生效版：用于「使用模板」，不是当前修订版指针。"""
    for version in reversed(list(template.versions)):
        if version.status == DeliverableStatus.EFFECTIVE.value:
            return version
    return None


# ------------------------------------------------------------------ 调用与复制


def log_usage(
    db: Session,
    template: ToolTemplate,
    version: ToolTemplateVersion,
    mode: str,
    user: User,
    *,
    project_id: Optional[int] = None,
    deliverable_instance_id: Optional[int] = None,
    deliverable_version_id: Optional[int] = None,
    context: Optional[dict] = None,
    note: Optional[str] = None,
) -> TemplateUsage:
    usage = TemplateUsage(
        template_id=template.id,
        template_version_id=version.id,
        mode=mode,
        project_id=project_id,
        deliverable_instance_id=deliverable_instance_id,
        deliverable_version_id=deliverable_version_id,
        context_json=context or {},
        created_by=user.display_name,
        created_by_id=user.id,
        note=note,
    )
    db.add(usage)
    db.flush()
    return usage


def copy_to_deliverable(
    db: Session,
    template: ToolTemplate,
    version: ToolTemplateVersion,
    instance: DeliverableInstance,
    project: Project,
    user: User,
    *,
    title: Optional[str] = None,
    note: Optional[str] = None,
) -> Tuple[DeliverableVersion, TemplateUsage]:
    """把模板版本复制成项目交付物的一个新版本，并记录来源与使用记录。"""
    if version.status != DeliverableStatus.EFFECTIVE.value:
        raise TemplateError("只能使用已生效的模板版本")
    if (
        template.deliverable_definition_id is not None
        and template.deliverable_definition_id != instance.definition_id
    ):
        raise TemplateError("模板产出的交付物与目标步骤不一致")

    context = resolve_context(db, version, project, instance)
    payload: Dict[str, Any] = {
        "title": title or template.name,
        "note": note
        or f"基于模板 {template.code} {version.version_label}（{FORMAT_LABELS.get(template.format, template.format)}）",
        "source_template_version_id": version.id,
    }
    mode = TemplateMode.ONLINE.value
    storage_key = None
    storage = storage_service.get_storage()

    if template.format == TemplateFormat.ONLINE.value:
        mode = TemplateMode.ONLINE.value
    elif version.storage_key:
        mode = TemplateMode.DOWNLOAD.value
        try:
            source = storage.open(version.storage_key)
        except FileNotFoundError as exc:
            raise TemplateError("模板文件不存在或已被清理") from exc
        try:
            storage_key = storage_service.build_key(
                f"deliverables/{project.id}/{instance.id}",
                version.file_name or f"{template.code}.{template.format.lower()}",
            )
            digest, size = storage.save(storage_key, source, storage_service.max_bytes())
        finally:
            source.close()
        payload.update(
            file_name=version.file_name,
            mime_type=version.mime_type,
            size_bytes=size,
            checksum=digest,
            storage_backend="local",
            storage_key=storage_key,
        )
    else:
        raise TemplateError("模板版本没有文件，无法复制")

    try:
        deliverable_version = deliverable_service.create_version(db, instance, payload, user)
    except Exception:
        if storage_key:
            storage.delete(storage_key)
        raise

    usage = log_usage(
        db,
        template,
        version,
        mode,
        user,
        project_id=project.id,
        deliverable_instance_id=instance.id,
        deliverable_version_id=deliverable_version.id,
        context=context.context,
        note=note,
    )
    return deliverable_version, usage


def resolve_context(
    db: Session,
    version: ToolTemplateVersion,
    project: Optional[Project],
    instance: Optional[DeliverableInstance] = None,
) -> TemplateContext:
    """按「模板声明的 source」解析实例上下文；不依赖模板自己问一遍字段。"""
    context: Dict[str, Any] = {"today": date.today().isoformat(), "now": utcnow().isoformat()}
    if project is not None:
        context.update(
            {
                "project.code": project.code,
                "project.name": project.name,
                "project.owner": project.owner,
                "project.department": project.department,
                "project.objective": project.objective,
                "project.metric_name": project.metric_name,
                "project.baseline_value": project.baseline_value,
                "project.target_value": project.target_value,
                "project.start_date": project.start_date.isoformat()
                if project.start_date
                else None,
                "project.end_date": project.end_date.isoformat() if project.end_date else None,
            }
        )
        if project.process_id:
            process = db.get(ProcessArch, project.process_id)
            if process is not None:
                context["process.code"] = process.code
                context["process.name"] = process.name
    if instance is not None:
        context.update(
            {
                "step.step_no": instance.step.step_no,
                "step.name": instance.step.name,
                "deliverable.code": instance.definition.code,
                "deliverable.name": instance.definition.name,
            }
        )

    placeholders: List[PlaceholderValue] = []
    missing: List[str] = []
    for raw in version.placeholders or []:
        if not isinstance(raw, dict) or not raw.get("key") or not raw.get("source"):
            continue
        value = context.get(raw["source"])
        text = None if value is None else str(value)
        is_missing = bool(raw.get("required")) and not text
        placeholders.append(
            PlaceholderValue(
                key=raw["key"],
                label=raw.get("label", ""),
                source=raw["source"],
                required=bool(raw.get("required")),
                format=raw.get("format"),
                value=text,
                missing=is_missing,
            )
        )
        if is_missing:
            missing.append(raw["key"])
    return TemplateContext(context=context, placeholders=placeholders, missing_required=missing)


# ------------------------------------------------------------------ 出参


def version_out(version: ToolTemplateVersion) -> ToolTemplateVersionOut:
    has_file = bool(version.storage_key)
    return ToolTemplateVersionOut(
        id=version.id,
        template_id=version.template_id,
        version_label=version.version_label,
        status=version.status,
        status_label=deliverable_service.STATUS_LABELS.get(version.status, version.status),
        note=version.note,
        file_name=version.file_name,
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        checksum=version.checksum,
        storage_backend=version.storage_backend,
        has_file=has_file,
        download_url=(
            f"{settings.api_prefix}/tool-templates/{version.template_id}"
            f"/versions/{version.id}/download"
            if has_file
            else None
        ),
        placeholders=version.placeholders or [],
        base_version_id=version.base_version_id,
        created_by=version.created_by,
        approved_by=version.approved_by,
        approved_at=version.approved_at,
        valid_from=version.valid_from,
        valid_to=version.valid_to,
        created_at=version.created_at,
    )


def template_out(template: ToolTemplate) -> ToolTemplateOut:
    versions = list(template.versions)
    current = next((v for v in versions if v.id == template.current_version_id), None)
    effective = next(
        (v for v in reversed(versions) if v.status == DeliverableStatus.EFFECTIVE.value), None
    )
    return ToolTemplateOut(
        id=template.id,
        tool_code=template.tool_code,
        tool_name=template.tool.name if template.tool else None,
        stage_no=template.tool.stage_no if template.tool else None,
        code=template.code,
        name=template.name,
        format=template.format,
        format_label=FORMAT_LABELS.get(template.format, template.format),
        description=template.description,
        instructions=template.instructions,
        deliverable_definition_id=template.deliverable_definition_id,
        deliverable_definition_name=template.definition.name if template.definition else None,
        owner=template.owner,
        owner_user_id=template.owner_user_id,
        **org_service.resolve_scope(template.org_unit),
        review_date=template.review_date,
        review_overdue=bool(
            template.review_date and template.review_date < date.today() and template.is_active
        ),
        is_default=template.is_default,
        is_active=template.is_active,
        current_version_id=template.current_version_id,
        current_version=version_out(current) if current else None,
        effective_version=version_out(effective) if effective else None,
        version_count=len(versions),
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def template_detail(template: ToolTemplate) -> ToolTemplateDetail:
    base = template_out(template)
    return ToolTemplateDetail(
        **base.model_dump(),
        versions=[version_out(v) for v in template.versions],
    )


def usage_out(usage: TemplateUsage) -> TemplateUsageOut:
    return TemplateUsageOut(
        id=usage.id,
        template_id=usage.template_id,
        template_code=usage.template_version.template.code
        if usage.template_version and usage.template_version.template
        else None,
        template_version_id=usage.template_version_id,
        version_label=usage.template_version.version_label if usage.template_version else None,
        mode=usage.mode,
        mode_label=MODE_LABELS.get(usage.mode, usage.mode),
        project_id=usage.project_id,
        project_code=usage.project.code if usage.project else None,
        deliverable_instance_id=usage.deliverable_instance_id,
        deliverable_version_id=usage.deliverable_version_id,
        created_by=usage.created_by,
        note=usage.note,
        created_at=usage.created_at,
    )


def meta() -> TemplateMeta:
    return TemplateMeta(
        format_labels=FORMAT_LABELS,
        status_labels=deliverable_service.STATUS_LABELS,
        mode_labels=MODE_LABELS,
        transitions=deliverable_service.ALLOWED_TRANSITIONS,
    )


def step_recommendations(db: Session, step_no: str) -> StepRecommendationOut:
    """步骤页的「推荐工具 + 模板」：契约决定工具与使用要求，模板按工具归组。"""
    step = db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.step_no == step_no))
    if step is None:
        raise TemplateError(f"标准步骤 {step_no} 不存在")
    contract = db.scalar(select(StepContract).where(StepContract.step_no == step_no))
    codes = list(contract.tool_codes or []) if contract else []
    levels = deliverable_service.normalized_tool_levels(
        codes, contract.tool_levels if contract else None
    )

    tools = (
        {tool.code: tool for tool in db.scalars(select(Tool).where(Tool.code.in_(codes))).all()}
        if codes
        else {}
    )
    template_stmt = (
        select(ToolTemplate)
        .options(
            joinedload(ToolTemplate.tool),
            joinedload(ToolTemplate.definition),
            selectinload(ToolTemplate.versions),
        )
        .where(ToolTemplate.is_active.is_(True))
        .order_by(ToolTemplate.tool_code, ToolTemplate.is_default.desc(), ToolTemplate.id)
    )
    if codes:
        template_stmt = template_stmt.where(ToolTemplate.tool_code.in_(codes))
    by_tool: Dict[str, List[ToolTemplate]] = {}
    for template in db.scalars(template_stmt).all():
        by_tool.setdefault(template.tool_code, []).append(template)

    recommended: List[RecommendedToolOut] = []
    for code in codes:
        tool = tools.get(code)
        if tool is None:
            continue
        level = levels.get(code, ToolLevel.RECOMMENDED.value)
        recommended.append(
            RecommendedToolOut(
                code=tool.code,
                name=tool.name,
                category=tool.category,
                category_label=deliverable_service.TOOL_CATEGORY_LABELS.get(
                    tool.category, tool.category
                ),
                stage_no=tool.stage_no,
                level=level,
                level_label=deliverable_service.TOOL_LEVEL_LABELS.get(level, level),
                templates=[template_out(t) for t in by_tool.get(code, [])],
            )
        )

    definitions = db.scalars(
        select(DeliverableDefinition).where(DeliverableDefinition.step_no == step_no)
    ).all()
    definition_ids = [d.id for d in definitions]
    extras: List[ToolTemplate] = []
    if definition_ids:
        extra_stmt = (
            select(ToolTemplate)
            .options(
                joinedload(ToolTemplate.tool),
                joinedload(ToolTemplate.definition),
                selectinload(ToolTemplate.versions),
            )
            .where(
                ToolTemplate.is_active.is_(True),
                ToolTemplate.deliverable_definition_id.in_(definition_ids),
            )
            .order_by(ToolTemplate.tool_code, ToolTemplate.id)
        )
        if codes:
            extra_stmt = extra_stmt.where(ToolTemplate.tool_code.notin_(codes))
        extras = list(db.scalars(extra_stmt).all())

    return StepRecommendationOut(
        step_no=step.step_no,
        step_name=step.name,
        stage_no=step.stage_no,
        tools=recommended,
        deliverable_templates=[template_out(t) for t in extras],
    )
