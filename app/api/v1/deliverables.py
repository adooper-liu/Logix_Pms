"""步骤契约与交付物 API。

标准侧（契约、交付物定义）只有 MANAGER+ 能改；项目侧的版本操作跟随项目的
`owner_user_id` 归属校验，与步骤更新保持同一套权限语义。
"""

from __future__ import annotations

import mimetypes
import re
from datetime import date
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import joinedload, selectinload
from starlette.background import BackgroundTask

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    apply_owner_update,
    ensure_can_edit_owned,
)
from app.core.config import settings
from app.models.deliverable import (
    DeliverableDefinition,
    DeliverableInstance,
    DeliverableVersion,
)
from app.models.enums import DeliverableStatus
from app.models.project import Project, WorkflowTemplate
from app.schemas.common import DeleteResult, as_columns
from app.schemas.deliverable import (
    DeliverableDefinitionCreate,
    DeliverableDefinitionOut,
    DeliverableDefinitionUpdate,
    DeliverableInstanceDetail,
    DeliverableInstanceOut,
    DeliverableInstanceUpdate,
    DeliverableMeta,
    DeliverableSummary,
    DeliverableSyncResult,
    DeliverableVersionCreate,
    DeliverableVersionOut,
    DeliverableVersionTransition,
    StepContractOut,
    StepContractUpdate,
    StepRecommendationOut,
)
from app.services import audit as audit_service
from app.services import deliverable as deliverable_service
from app.services import storage as storage_service
from app.services import tool_template as template_service

standard_router = APIRouter(prefix="/workflow", tags=["步骤契约"])
project_router = APIRouter(prefix="/projects", tags=["交付物"])
router = APIRouter(prefix="/deliverables", tags=["交付物"])


def _fail(exc: deliverable_service.DeliverableError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# ------------------------------------------------------------------ 标准侧


@standard_router.get("/contracts", response_model=List[StepContractOut], summary="全部步骤契约")
def list_contracts(db: DbSession):
    rows = db.scalars(
        select(WorkflowTemplate).order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)
    ).all()
    return [deliverable_service.get_contract(db, row.step_no) for row in rows]


@standard_router.get(
    "/steps/{step_no}/contract", response_model=StepContractOut, summary="单步契约与交付物定义"
)
def get_contract(step_no: str, db: DbSession):
    try:
        return deliverable_service.get_contract(db, step_no)
    except deliverable_service.DeliverableError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@standard_router.get(
    "/steps/{step_no}/recommendations",
    response_model=StepRecommendationOut,
    summary="本步骤推荐工具与预制模板",
)
def step_recommendations(step_no: str, db: DbSession):
    try:
        return template_service.step_recommendations(db, step_no)
    except template_service.TemplateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@standard_router.put(
    "/steps/{step_no}/contract", response_model=StepContractOut, summary="维护步骤契约（MANAGER+）"
)
def update_contract(step_no: str, payload: StepContractUpdate, db: DbSession, user: ManagerUser):
    data = payload.model_dump(exclude_unset=True)
    try:
        contract = deliverable_service.save_contract(db, step_no, data, user)
    except deliverable_service.DeliverableError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "step_contract",
        contract.id,
        f"更新步骤 {step_no} 契约：{', '.join(sorted(data.keys())) or '（无变更）'}",
    )
    db.commit()
    return deliverable_service.get_contract(db, step_no)


@standard_router.get(
    "/deliverable-definitions",
    response_model=List[DeliverableDefinitionOut],
    summary="交付物定义清单",
)
def list_definitions(
    db: DbSession,
    step_no: Optional[str] = None,
    include_inactive: bool = Query(default=False),
):
    stmt = select(DeliverableDefinition)
    if step_no:
        stmt = stmt.where(DeliverableDefinition.step_no == step_no)
    if not include_inactive:
        stmt = stmt.where(DeliverableDefinition.is_active.is_(True))
    rows = db.scalars(
        stmt.order_by(DeliverableDefinition.step_no, DeliverableDefinition.sort_order)
    ).all()
    return [deliverable_service.definition_out(row) for row in rows]


@standard_router.post(
    "/deliverable-definitions",
    response_model=DeliverableDefinitionOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增交付物定义（MANAGER+）",
)
def create_definition(payload: DeliverableDefinitionCreate, db: DbSession, user: ManagerUser):
    try:
        deliverable_service.require_step(db, payload.step_no)
    except deliverable_service.DeliverableError as exc:
        raise _fail(exc) from exc
    code = payload.code or deliverable_service.next_definition_code(db, payload.step_no)
    if db.scalar(select(DeliverableDefinition).where(DeliverableDefinition.code == code)):
        raise HTTPException(status_code=409, detail=f"交付物编码 {code} 已存在")
    data = as_columns(payload.model_dump(exclude={"code"}))
    definition = DeliverableDefinition(code=code, **data)
    db.add(definition)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "deliverable_definition",
        definition.id,
        f"新增交付物定义 {code}（步骤 {payload.step_no}）",
    )
    db.commit()
    db.refresh(definition)
    return deliverable_service.definition_out(definition)


@standard_router.patch(
    "/deliverable-definitions/{definition_id}",
    response_model=DeliverableDefinitionOut,
    summary="修改交付物定义（MANAGER+）",
)
def update_definition(
    definition_id: int,
    payload: DeliverableDefinitionUpdate,
    db: DbSession,
    user: ManagerUser,
):
    definition = db.get(DeliverableDefinition, definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="交付物定义不存在")
    data = as_columns(payload.model_dump(exclude_unset=True))
    for field, value in data.items():
        if value is None and field in {"name", "type", "required", "sort_order", "is_active"}:
            continue
        setattr(definition, field, value)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "deliverable_definition",
        definition.id,
        f"更新交付物定义 {definition.code}：{', '.join(sorted(data.keys())) or '（无变更）'}",
    )
    db.commit()
    db.refresh(definition)
    return deliverable_service.definition_out(definition)


@standard_router.delete(
    "/deliverable-definitions/{definition_id}",
    response_model=DeleteResult,
    summary="删除交付物定义（仅无项目实例时，MANAGER+）",
)
def delete_definition(definition_id: int, db: DbSession, user: ManagerUser):
    definition = db.get(DeliverableDefinition, definition_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="交付物定义不存在")
    used = (
        db.scalar(
            select(func.count())
            .select_from(DeliverableInstance)
            .where(DeliverableInstance.definition_id == definition_id)
        )
        or 0
    )
    if used:
        raise HTTPException(
            status_code=409,
            detail=f"该定义已被 {used} 个交付物实例引用，请停用（is_active=false）而不是删除",
        )
    code = definition.code
    audit_service.record(
        db, user, "DELETE", "deliverable_definition", definition.id, f"删除交付物定义 {code}"
    )
    db.delete(definition)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 项目侧


def _get_project(db: DbSession, project_id: int) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _get_instance(db: DbSession, instance_id: int) -> DeliverableInstance:
    instance = db.get(DeliverableInstance, instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="交付物实例不存在")
    return instance


def _project_of(db: DbSession, instance: DeliverableInstance) -> Project:
    project = db.get(Project, instance.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


def _get_version(
    db: DbSession, instance: DeliverableInstance, version_id: int
) -> DeliverableVersion:
    version = db.get(DeliverableVersion, version_id)
    if version is None or version.instance_id != instance.id:
        raise HTTPException(status_code=404, detail="交付物版本不存在")
    return version


@project_router.get(
    "/{project_id}/deliverables",
    response_model=List[DeliverableInstanceOut],
    summary="项目交付物清单（含当前版本）",
)
def list_project_deliverables(
    project_id: int,
    db: DbSession,
    status_: Optional[DeliverableStatus] = Query(default=None, alias="status"),
    required: Optional[bool] = None,
):
    _get_project(db, project_id)
    stmt = (
        select(DeliverableInstance)
        .options(
            joinedload(DeliverableInstance.definition),
            joinedload(DeliverableInstance.project),
            joinedload(DeliverableInstance.step),
            selectinload(DeliverableInstance.versions),
        )
        .where(DeliverableInstance.project_id == project_id)
    )
    if status_ is not None:
        stmt = stmt.where(DeliverableInstance.status == status_.value)
    if required is not None:
        stmt = stmt.join(
            DeliverableDefinition, DeliverableDefinition.id == DeliverableInstance.definition_id
        ).where(DeliverableDefinition.required.is_(required))
    instances = db.scalars(stmt.order_by(DeliverableInstance.project_step_id)).all()
    return [deliverable_service.instance_out(i) for i in instances]


@project_router.get(
    "/{project_id}/deliverables/summary",
    response_model=DeliverableSummary,
    summary="项目交付物完成度",
)
def project_deliverable_summary(project_id: int, db: DbSession):
    _get_project(db, project_id)
    return deliverable_service.project_summary(db, project_id)


@project_router.post(
    "/{project_id}/deliverables/sync",
    response_model=DeliverableSyncResult,
    summary="按当前定义补齐缺失的交付物实例（幂等）",
)
def sync_project_deliverables(project_id: int, db: DbSession, user: WriteUser):
    project = _get_project(db, project_id)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    created = deliverable_service.sync_project_instances(db, project)
    total = (
        db.scalar(
            select(func.count())
            .select_from(DeliverableInstance)
            .where(DeliverableInstance.project_id == project_id)
        )
        or 0
    )
    audit_service.record(
        db,
        user,
        "CREATE",
        "project",
        project.id,
        f"{project.code} 补齐交付物实例 {created} 个（共 {total}）",
    )
    db.commit()
    return DeliverableSyncResult(created=created, total=total)


# ------------------------------------------------------------------ 交付物实例


@router.get("/meta", response_model=DeliverableMeta, summary="交付物类型 / 状态中文标签与状态机")
def deliverable_meta():
    return DeliverableMeta(
        type_labels=deliverable_service.TYPE_LABELS,
        status_labels=deliverable_service.STATUS_LABELS,
        transitions=deliverable_service.ALLOWED_TRANSITIONS,
    )


@router.get(
    "/{instance_id}", response_model=DeliverableInstanceDetail, summary="交付物详情（含全部版本）"
)
def get_instance(instance_id: int, db: DbSession):
    instance = _get_instance(db, instance_id)
    return deliverable_service.instance_detail(db, instance)


@router.patch("/{instance_id}", response_model=DeliverableInstanceOut, summary="调整交付物负责人")
def update_instance(
    instance_id: int, payload: DeliverableInstanceUpdate, db: DbSession, user: WriteUser
):
    instance = _get_instance(db, instance_id)
    project = _project_of(db, instance)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    data = as_columns(payload.model_dump(exclude_unset=True))
    apply_owner_update(db, data, instance.owner)
    for field, value in data.items():
        setattr(instance, field, value)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "deliverable_instance",
        instance.id,
        f"{project.code} 交付物 {instance.definition.code} 负责人改为 {instance.owner or '未指定'}",
    )
    db.commit()
    db.refresh(instance)
    return deliverable_service.instance_out(instance)


@router.get(
    "/{instance_id}/versions",
    response_model=List[DeliverableVersionOut],
    summary="交付物版本历史（只追加不覆盖）",
)
def list_versions(instance_id: int, db: DbSession):
    instance = _get_instance(db, instance_id)
    rows = db.scalars(
        select(DeliverableVersion)
        .where(DeliverableVersion.instance_id == instance.id)
        .order_by(DeliverableVersion.version_no)
    ).all()
    return [deliverable_service.version_out(v) for v in rows]


@router.post(
    "/{instance_id}/versions",
    response_model=DeliverableVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="登记新版本（自动递增 R1/R2…）",
)
def create_version(
    instance_id: int, payload: DeliverableVersionCreate, db: DbSession, user: WriteUser
):
    instance = _get_instance(db, instance_id)
    project = _project_of(db, instance)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    try:
        version = deliverable_service.create_version(
            db, instance, payload.model_dump(exclude_unset=True), user
        )
    except deliverable_service.DeliverableError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "deliverable_version",
        version.id,
        f"{project.code} 交付物 {instance.definition.code} 登记 R{version.version_no}",
    )
    db.commit()
    db.refresh(version)
    return deliverable_service.version_out(version)


@router.post(
    "/{instance_id}/versions/upload",
    response_model=DeliverableVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="上传新版本文件（服务端计算 SHA-256）",
)
def upload_version(
    instance_id: int,
    db: DbSession,
    user: WriteUser,
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    note: Optional[str] = Form(default=None),
    checksum: Optional[str] = Form(default=None),
    valid_from: Optional[date] = Form(default=None),
    base_version_id: Optional[int] = Form(default=None),
    source_document_version_id: Optional[int] = Form(default=None),
):
    instance = _get_instance(db, instance_id)
    project = _project_of(db, instance)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)

    if checksum and not re.fullmatch(r"[0-9a-fA-F]{64}", checksum):
        raise HTTPException(status_code=400, detail="checksum 必须是 64 位十六进制 SHA-256")

    try:
        filename = storage_service.validate_filename(
            file.filename or "", settings.attachment_allowed_extensions
        )
        storage_service.verify_magic(file.file, filename)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = storage_service.get_storage()
    key = storage_service.build_key(f"deliverables/{project.id}/{instance.id}", filename)
    try:
        digest, size = storage.save(key, file.file, storage_service.max_bytes())
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if checksum and checksum.lower() != digest:
        storage.delete(key)
        raise HTTPException(status_code=400, detail="文件校验值与客户端提供的 SHA-256 不一致")

    payload = {
        "title": title,
        "note": note,
        "file_name": filename,
        "mime_type": file.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream",
        "size_bytes": size,
        "checksum": digest,
        "storage_backend": "local",
        "storage_key": key,
        "valid_from": valid_from,
        "base_version_id": base_version_id,
        "source_document_version_id": source_document_version_id,
    }
    try:
        version = deliverable_service.create_version(db, instance, payload, user)
    except deliverable_service.DeliverableError as exc:
        db.rollback()
        storage.delete(key)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        storage.delete(key)
        raise

    try:
        audit_service.record(
            db,
            user,
            "CREATE",
            "deliverable_version",
            version.id,
            f"{project.code} 交付物 {instance.definition.code} 上传 R{version.version_no}"
            f"（{filename}, {size} bytes, sha256={digest[:12]}…）",
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(version)
    return deliverable_service.version_out(version)


@router.get(
    "/{instance_id}/versions/{version_id}/download",
    summary="下载版本文件（attachment + nosniff）",
)
def download_version(instance_id: int, version_id: int, db: DbSession, user: CurrentUser):
    instance = _get_instance(db, instance_id)
    version = _get_version(db, instance, version_id)
    if not version.storage_key:
        raise HTTPException(status_code=404, detail="该版本没有上传文件")

    storage = storage_service.get_storage()
    try:
        handle = storage.open(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在或已被清理") from exc
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = version.file_name or f"R{version.version_no}"
    audit_service.record(
        db,
        user,
        "DOWNLOAD",
        "deliverable_version",
        version.id,
        f"下载交付物 {instance.definition.code} R{version.version_no}（{filename}）",
    )
    db.commit()
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


@router.post(
    "/{instance_id}/versions/{version_id}/transition",
    response_model=DeliverableVersionOut,
    summary="审批流转：DRAFT → IN_REVIEW → APPROVED → EFFECTIVE",
)
def transition_version(
    instance_id: int,
    version_id: int,
    payload: DeliverableVersionTransition,
    db: DbSession,
    user: WriteUser,
):
    instance = _get_instance(db, instance_id)
    project = _project_of(db, instance)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    version = _get_version(db, instance, version_id)
    previous = version.status
    try:
        version = deliverable_service.transition_version(
            db, instance, version, payload.status.value, user, payload.note
        )
    except deliverable_service.DeliverableError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "deliverable_version",
        version.id,
        f"{project.code} 交付物 {instance.definition.code} R{version.version_no}："
        f"{previous} → {version.status}" + (f"（{payload.note}）" if payload.note else ""),
    )
    db.commit()
    db.refresh(version)
    return deliverable_service.version_out(version)


@router.post(
    "/{instance_id}/versions/{version_id}/restore",
    response_model=DeliverableInstanceDetail,
    summary="恢复历史版本（移动当前版本指针，不复制文件）",
)
def restore_version(instance_id: int, version_id: int, db: DbSession, user: WriteUser):
    instance = _get_instance(db, instance_id)
    project = _project_of(db, instance)
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)
    version = _get_version(db, instance, version_id)
    try:
        deliverable_service.restore_version(db, instance, version, user)
    except deliverable_service.DeliverableError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "deliverable_version",
        version.id,
        f"{project.code} 交付物 {instance.definition.code} 恢复为 R{version.version_no}",
    )
    db.commit()
    db.refresh(instance)
    return deliverable_service.instance_detail(db, instance)
