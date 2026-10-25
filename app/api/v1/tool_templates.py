"""工具预制模板 API：模板库、版本、下载、调用记录、复制到项目。

模板是受控的方法资产：管理接口只对 MANAGER+ 开放；项目侧复制跟随项目 Owner；
下载与引用查看对登录用户开放并记录使用。
"""

from __future__ import annotations

import mimetypes
import re
from datetime import date
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.orm import joinedload, selectinload
from starlette.background import BackgroundTask

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    apply_owner_update,
    ensure_can_edit_owned,
    resolve_owner,
)
from app.core.config import settings
from app.models.deliverable import DeliverableDefinition, DeliverableInstance
from app.models.enums import TemplateFormat, TemplateMode
from app.models.project import Project
from app.models.tool import Tool
from app.models.tool_template import TemplateUsage, ToolTemplate, ToolTemplateVersion
from app.schemas.common import DeleteResult, as_columns
from app.schemas.deliverable import DeliverableVersionOut
from app.schemas.tool_template import (
    PlaceholderSpec,
    TemplateContext,
    TemplateCopyRequest,
    TemplateMeta,
    TemplateUsageOut,
    TemplateUseRequest,
    ToolTemplateCreate,
    ToolTemplateDetail,
    ToolTemplateOut,
    ToolTemplateUpdate,
    ToolTemplateVersionCreate,
    ToolTemplateVersionOut,
    ToolTemplateVersionTransition,
)
from app.services import audit as audit_service
from app.services import deliverable as deliverable_service
from app.services import org_scope
from app.services import org_unit as org_service
from app.services import preview as preview_service
from app.services import storage as storage_service
from app.services import tool_template as template_service

router = APIRouter(prefix="/tool-templates", tags=["工具模板库"])

_PLACEHOLDERS = TypeAdapter(List[PlaceholderSpec])


def _fail(exc: template_service.TemplateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _get(db: DbSession, template_id: int) -> ToolTemplate:
    template = db.get(ToolTemplate, template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="模板不存在")
    return template


def _get_version(db: DbSession, template: ToolTemplate, version_id: int) -> ToolTemplateVersion:
    version = db.get(ToolTemplateVersion, version_id)
    if version is None or version.template_id != template.id:
        raise HTTPException(status_code=404, detail="模板版本不存在")
    return version


def _require_effective(template: ToolTemplate) -> ToolTemplateVersion:
    version = template_service.effective_version(template)
    if version is None:
        raise HTTPException(status_code=409, detail="该模板还没有已生效版本，请先完成审批")
    return version


def _parse_placeholders(raw: Optional[str]) -> List[dict]:
    if not raw:
        return []
    try:
        return [item.model_dump() for item in _PLACEHOLDERS.validate_json(raw)]
    except ValidationError as exc:
        raise HTTPException(
            status_code=400, detail=f"placeholders 格式不正确：{exc.errors()[0]['msg']}"
        ) from exc


# ------------------------------------------------------------------ 模板库


@router.get("/meta", response_model=TemplateMeta, summary="模板格式 / 状态 / 调用方式标签")
def template_meta():
    return template_service.meta()


@router.get(
    "", response_model=List[ToolTemplateOut], summary="模板库（可按工具 / 阶段 / 格式筛选）"
)
def list_templates(
    db: DbSession,
    tool_code: Optional[str] = None,
    format: Optional[TemplateFormat] = None,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
    deliverable_definition_id: Optional[int] = None,
    org_unit_id: Optional[int] = Query(
        default=None, description="按组织范围过滤：集团通用 + 本级 + 上级继承"
    ),
    keyword: Optional[str] = None,
    active_only: bool = True,
):
    stmt = (
        select(ToolTemplate)
        .options(
            joinedload(ToolTemplate.tool),
            joinedload(ToolTemplate.definition),
            joinedload(ToolTemplate.org_unit),
            selectinload(ToolTemplate.versions),
        )
        .order_by(ToolTemplate.tool_code, ToolTemplate.is_default.desc(), ToolTemplate.id)
    )
    stmt = org_scope.scoped(db, stmt, ToolTemplate.org_unit_id, org_unit_id)
    if tool_code:
        stmt = stmt.where(ToolTemplate.tool_code == tool_code)
    if format is not None:
        stmt = stmt.where(ToolTemplate.format == format.value)
    if stage_no is not None:
        stmt = stmt.join(Tool, Tool.code == ToolTemplate.tool_code).where(Tool.stage_no == stage_no)
    if deliverable_definition_id is not None:
        stmt = stmt.where(ToolTemplate.deliverable_definition_id == deliverable_definition_id)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                ToolTemplate.name.like(like),
                ToolTemplate.code.like(like),
                ToolTemplate.description.like(like),
            )
        )
    if active_only:
        stmt = stmt.where(ToolTemplate.is_active.is_(True))
    return [template_service.template_out(row) for row in db.scalars(stmt).all()]


@router.get("/{template_id}", response_model=ToolTemplateDetail, summary="模板详情与全部版本")
def get_template(template_id: int, db: DbSession):
    return template_service.template_detail(_get(db, template_id))


@router.post(
    "",
    response_model=ToolTemplateOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建模板（MANAGER+）",
)
def create_template(payload: ToolTemplateCreate, db: DbSession, user: ManagerUser):
    try:
        template_service.require_tool(db, payload.tool_code)
    except template_service.TemplateError as exc:
        raise _fail(exc) from exc
    code = payload.code or template_service.next_template_code(db, payload.tool_code)
    if db.scalar(select(ToolTemplate).where(ToolTemplate.code == code)):
        raise HTTPException(status_code=409, detail=f"模板编码 {code} 已存在")
    data = as_columns(payload.model_dump(exclude={"code", "is_default"}))
    if data.get("org_unit_id") is not None:
        try:
            org_service.require_org(db, data["org_unit_id"])
        except org_service.OrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.get("deliverable_definition_id") is not None:
        if db.get(DeliverableDefinition, data["deliverable_definition_id"]) is None:
            raise HTTPException(
                status_code=400, detail="deliverable_definition_id 指向的交付物不存在"
            )
    data["owner_user_id"], data["owner"] = resolve_owner(
        db, data.get("owner_user_id"), data.get("owner")
    )
    template = template_service.create_template(db, {"code": code, **data})
    has_default = (
        db.scalar(
            select(func.count())
            .select_from(ToolTemplate)
            .where(
                ToolTemplate.tool_code == template.tool_code,
                ToolTemplate.format == template.format,
                ToolTemplate.is_default.is_(True),
            )
        )
        or 0
    )
    if payload.is_default or not has_default:
        template_service.set_default(db, template)
    audit_service.record(
        db,
        user,
        "CREATE",
        "tool_template",
        template.id,
        f"新建模板 {code}（{payload.tool_code} / {payload.format.value}）",
    )
    db.commit()
    db.refresh(template)
    return template_service.template_out(template)


@router.patch(
    "/{template_id}", response_model=ToolTemplateOut, summary="修改模板元数据（MANAGER+）"
)
def update_template(
    template_id: int, payload: ToolTemplateUpdate, db: DbSession, user: ManagerUser
):
    template = _get(db, template_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    if data.get("org_unit_id") is not None:
        try:
            org_service.require_org(db, data["org_unit_id"])
        except org_service.OrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.get("deliverable_definition_id") is not None:
        if db.get(DeliverableDefinition, data["deliverable_definition_id"]) is None:
            raise HTTPException(
                status_code=400, detail="deliverable_definition_id 指向的交付物不存在"
            )
    apply_owner_update(db, data, template.owner)
    make_default = data.pop("is_default", None)
    for field, value in data.items():
        if value is None and field in {"name", "is_active"}:
            continue
        setattr(template, field, value)
    if make_default is True:
        template_service.set_default(db, template)
    elif make_default is False:
        template.is_default = False
    db.flush()
    if make_default is False or data.get("is_active") is False:
        template_service.ensure_default(db, template.tool_code, template.format)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "tool_template",
        template.id,
        f"更新模板 {template.code}：{', '.join(sorted(data.keys())) or '（无变更）'}",
    )
    db.commit()
    db.refresh(template)
    return template_service.template_out(template)


@router.delete(
    "/{template_id}", response_model=DeleteResult, summary="删除模板（无版本/使用记录时，MANAGER+）"
)
def delete_template(template_id: int, db: DbSession, user: ManagerUser):
    template = _get(db, template_id)
    versions = (
        db.scalar(
            select(func.count())
            .select_from(ToolTemplateVersion)
            .where(ToolTemplateVersion.template_id == template.id)
        )
        or 0
    )
    usages = (
        db.scalar(
            select(func.count())
            .select_from(TemplateUsage)
            .where(TemplateUsage.template_id == template.id)
        )
        or 0
    )
    if versions or usages:
        raise HTTPException(
            status_code=409,
            detail=f"模板已有 {versions} 个版本、{usages} 条使用记录，请停用（is_active=false）而不是删除",
        )
    code = template.code
    tool_code, template_format = template.tool_code, template.format
    audit_service.record(db, user, "DELETE", "tool_template", template.id, f"删除模板 {code}")
    db.delete(template)
    db.flush()
    template_service.ensure_default(db, tool_code, template_format)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 版本


@router.get(
    "/{template_id}/versions",
    response_model=List[ToolTemplateVersionOut],
    summary="模板版本历史",
)
def list_versions(template_id: int, db: DbSession):
    template = _get(db, template_id)
    return [template_service.version_out(v) for v in template.versions]


@router.post(
    "/{template_id}/versions",
    response_model=ToolTemplateVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增在线模板版本（MANAGER+；文件格式请走 upload）",
)
def create_online_version(
    template_id: int, payload: ToolTemplateVersionCreate, db: DbSession, user: ManagerUser
):
    template = _get(db, template_id)
    if template.format != TemplateFormat.ONLINE.value:
        raise HTTPException(status_code=400, detail="文件类模板必须通过 /versions/upload 上传文件")
    try:
        version = template_service.create_version(db, template, payload.model_dump(), user)
    except template_service.TemplateError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "tool_template_version",
        version.id,
        f"模板 {template.code} 新增在线版本 {version.version_label}",
    )
    db.commit()
    db.refresh(version)
    return template_service.version_out(version)


@router.post(
    "/{template_id}/versions/upload",
    response_model=ToolTemplateVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="上传模板版本文件（MANAGER+，服务端算 SHA-256）",
)
def upload_version(
    template_id: int,
    db: DbSession,
    user: ManagerUser,
    file: UploadFile = File(...),
    version_label: str = Form(...),
    note: Optional[str] = Form(default=None),
    placeholders: Optional[str] = Form(default=None, description="JSON 数组"),
    valid_from: Optional[date] = Form(default=None),
    base_version_id: Optional[int] = Form(default=None),
):
    template = _get(db, template_id)
    if template.format == TemplateFormat.ONLINE.value:
        raise HTTPException(status_code=400, detail="在线模板不需要上传文件，请走 /versions")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version_label):
        raise HTTPException(status_code=400, detail="version_label 必须形如 1.0.0")

    try:
        filename = storage_service.validate_filename(
            file.filename or "", settings.attachment_allowed_extensions
        )
        if not template_service.format_accepts(filename, template.format):
            allowed = template_service.FORMAT_EXTENSIONS[template.format]
            raise template_service.TemplateError(
                f"{template.format} 模板只接受 {', '.join(allowed)}"
            )
        storage_service.verify_magic(file.file, filename)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except template_service.TemplateError as exc:
        raise _fail(exc) from exc

    specs = _parse_placeholders(placeholders)
    storage = storage_service.get_storage()
    key = storage_service.build_key(f"tool-templates/{template.id}", filename)
    try:
        checksum, size = storage.save(key, file.file, storage_service.max_bytes())
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = {
        "version_label": version_label,
        "note": note,
        "placeholders": specs,
        "valid_from": valid_from,
        "base_version_id": base_version_id,
    }
    file_meta = {
        "file_name": filename,
        "mime_type": file.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream",
        "size_bytes": size,
        "checksum": checksum,
        "storage_backend": "local",
        "storage_key": key,
    }
    try:
        version = template_service.create_version(db, template, data, user, file_meta)
    except template_service.TemplateError as exc:
        db.rollback()
        storage.delete(key)
        raise _fail(exc) from exc
    except Exception:
        db.rollback()
        storage.delete(key)
        raise

    try:
        audit_service.record(
            db,
            user,
            "CREATE",
            "tool_template_version",
            version.id,
            f"模板 {template.code} 上传版本 {version.version_label}"
            f"（{filename}, {size} bytes, sha256={checksum[:12]}…）",
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(version)
    return template_service.version_out(version)


@router.post(
    "/{template_id}/versions/{version_id}/transition",
    response_model=ToolTemplateVersionOut,
    summary="模板版本审批流转（MANAGER+）",
)
def transition_version(
    template_id: int,
    version_id: int,
    payload: ToolTemplateVersionTransition,
    db: DbSession,
    user: ManagerUser,
):
    template = _get(db, template_id)
    version = _get_version(db, template, version_id)
    previous = version.status
    try:
        version = template_service.transition_version(
            db, template, version, payload.status.value, user, payload.note
        )
    except template_service.TemplateError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "tool_template_version",
        version.id,
        f"模板 {template.code} {version.version_label}：{previous} → {version.status}"
        + (f"（{payload.note}）" if payload.note else ""),
    )
    db.commit()
    db.refresh(version)
    return template_service.version_out(version)


@router.get(
    "/{template_id}/versions/{version_id}/download",
    summary="下载模板版本文件（登录即可，记录使用）",
)
def download_version(template_id: int, version_id: int, db: DbSession, user: CurrentUser):
    template = _get(db, template_id)
    version = _get_version(db, template, version_id)
    if not version.storage_key:
        raise HTTPException(status_code=404, detail="该版本没有上传文件")

    storage = storage_service.get_storage()
    try:
        handle = storage.open(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在或已被清理") from exc
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    template_service.log_usage(
        db,
        template,
        version,
        TemplateMode.DOWNLOAD.value,
        user,
        note="通过下载接口使用模板",
    )
    audit_service.record(
        db,
        user,
        "DOWNLOAD",
        "tool_template_version",
        version.id,
        f"下载模板 {template.code} {version.version_label}",
    )
    db.commit()

    filename = version.file_name or f"{template.code}-{version.version_label}"
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        "X-Content-Type-Options": "nosniff",
    }
    if version.size_bytes is not None:
        headers["Content-Length"] = str(version.size_bytes)
    return StreamingResponse(
        handle,
        media_type=version.mime_type or "application/octet-stream",
        headers=headers,
        background=BackgroundTask(handle.close),
    )


@router.get(
    "/{template_id}/versions/{version_id}/preview",
    summary="预览模板版本（PDF/图片/文本内联）",
)
def preview_version(template_id: int, version_id: int, db: DbSession, user: CurrentUser):
    template = _get(db, template_id)
    version = _get_version(db, template, version_id)
    if not version.storage_key:
        raise HTTPException(status_code=404, detail="该版本没有上传文件")
    kind = preview_service.preview_kind(version.file_name, version.mime_type)
    if not kind:
        raise HTTPException(status_code=415, detail="该格式暂不支持在线预览，请下载后查看")

    storage = storage_service.get_storage()
    converted = preview_service.is_convertible(version.file_name, version.mime_type)
    if converted:
        try:
            handle = preview_service.ensure_pdf_preview(
                storage, version.storage_key, version.checksum, version.file_name
            )
        except preview_service.PreviewConversionError as exc:
            raise HTTPException(status_code=502, detail=f"转换预览失败：{exc}") from exc
        filename = preview_service.preview_filename(version.file_name, preview_service.PREVIEW_PDF)
        media_type = "application/pdf"
    else:
        try:
            handle = storage.open(version.storage_key)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="文件不存在或已被清理") from exc
        except storage_service.StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filename = version.file_name or f"{template.code}-{version.version_label}"
        media_type = preview_service.preview_media_type(kind, version.mime_type, version.file_name)

    headers = preview_service.inline_headers(filename)
    if not converted and version.size_bytes is not None:
        headers["Content-Length"] = str(version.size_bytes)
    return StreamingResponse(
        handle,
        media_type=media_type,
        headers=headers,
        background=BackgroundTask(handle.close),
    )


@router.get(
    "/{template_id}/versions/{version_id}/context",
    response_model=TemplateContext,
    summary="解析模板占位符在当前项目下的取值",
)
def version_context(
    template_id: int,
    version_id: int,
    db: DbSession,
    project_id: Optional[int] = None,
    deliverable_instance_id: Optional[int] = None,
):
    template = _get(db, template_id)
    version = _get_version(db, template, version_id)
    instance = None
    project = None
    if deliverable_instance_id is not None:
        instance = db.get(DeliverableInstance, deliverable_instance_id)
        if instance is None:
            raise HTTPException(status_code=404, detail="交付物实例不存在")
        project = db.get(Project, instance.project_id)
    elif project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
    return template_service.resolve_context(db, version, project, instance)


# ------------------------------------------------------------------ 调用与复制


@router.post(
    "/{template_id}/usages",
    response_model=TemplateUsageOut,
    summary="记录一次模板使用（引用查看 / 下载等）",
)
def record_usage(template_id: int, payload: TemplateUseRequest, db: DbSession, user: CurrentUser):
    template = _get(db, template_id)
    if payload.mode == TemplateMode.GENERATE:
        raise HTTPException(status_code=400, detail="服务端生成（GENERATE）尚未实现")
    version = _require_effective(template)

    project = None
    instance = None
    if payload.deliverable_instance_id is not None:
        instance = db.get(DeliverableInstance, payload.deliverable_instance_id)
        if instance is None:
            raise HTTPException(status_code=404, detail="交付物实例不存在")
        project = db.get(Project, instance.project_id)
        if payload.project_id is not None and payload.project_id != instance.project_id:
            raise HTTPException(status_code=400, detail="project_id 与交付物实例不一致")
    elif payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")

    context = template_service.resolve_context(db, version, project, instance)
    usage = template_service.log_usage(
        db,
        template,
        version,
        payload.mode.value,
        user,
        project_id=project.id if project else None,
        deliverable_instance_id=instance.id if instance else None,
        context=context.context,
        note=payload.note,
    )
    audit_service.record(
        db,
        user,
        "CREATE",
        "template_usage",
        usage.id,
        f"使用模板 {template.code} {version.version_label}（{payload.mode.value}）",
    )
    db.commit()
    db.refresh(usage)
    return template_service.usage_out(usage)


@router.post(
    "/{template_id}/copy",
    response_model=DeliverableVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="复制模板到项目交付物（固定来源版本）",
)
def copy_to_project(template_id: int, payload: TemplateCopyRequest, db: DbSession, user: WriteUser):
    template = _get(db, template_id)
    version = _require_effective(template)
    instance = db.get(DeliverableInstance, payload.deliverable_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="交付物实例不存在")
    project = db.get(Project, instance.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)

    try:
        version_out, usage = template_service.copy_to_deliverable(
            db,
            template,
            version,
            instance,
            project,
            user,
            title=payload.title,
            note=payload.note,
        )
    except template_service.TemplateError as exc:
        raise _fail(exc) from exc

    audit_service.record(
        db,
        user,
        "CREATE",
        "deliverable_version",
        version_out.id,
        f"{project.code} 交付物 {instance.definition.code} 从模板 "
        f"{template.code} {version.version_label} 复制为 R{version_out.version_no}",
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        if version_out.storage_key:
            storage_service.get_storage().delete(version_out.storage_key)
        raise
    db.refresh(version_out)
    return deliverable_service.version_out(version_out)


@router.get(
    "/{template_id}/usages",
    response_model=List[TemplateUsageOut],
    summary="模板使用记录（MANAGER+）",
)
def list_usages(
    template_id: int,
    db: DbSession,
    user: ManagerUser,
    limit: int = Query(default=100, ge=1, le=500),
):
    _get(db, template_id)
    rows = db.scalars(
        select(TemplateUsage)
        .where(TemplateUsage.template_id == template_id)
        .order_by(TemplateUsage.created_at.desc(), TemplateUsage.id.desc())
        .limit(limit)
    ).all()
    return [template_service.usage_out(row) for row in rows]
