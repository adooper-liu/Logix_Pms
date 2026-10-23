"""流程标准配套文件 API：挂在 L1–L4 节点上的 SOP / 表单 / 检查表。

- 文档与版本管理：MANAGER+
- 下载：登录即可，记录审计
- 复制到项目：跟随项目 Owner
- 项目成果晋升：MANAGER+，生成草稿后仍要走审批
"""

from __future__ import annotations

import mimetypes
import re
from datetime import date
from typing import List, Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
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
from app.models.deliverable import DeliverableInstance, DeliverableVersion
from app.models.enums import AssetVariationPolicy, ProcessDocumentCategory
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.project import Project
from app.schemas.common import DeleteResult, as_columns
from app.schemas.deliverable import DeliverableVersionOut
from app.schemas.process_document import (
    DocumentCopyRequest,
    DocumentImpactOut,
    DocumentPromoteRequest,
    DocumentRebaseRequest,
    EffectiveDocumentOut,
    ProcessDocumentCreate,
    ProcessDocumentDetail,
    ProcessDocumentMeta,
    ProcessDocumentOut,
    ProcessDocumentUpdate,
    ProcessDocumentVersionOut,
    ProcessDocumentVersionTransition,
)
from app.services import audit as audit_service
from app.services import deliverable as deliverable_service
from app.services import org_unit as org_service
from app.services import process_document as document_service
from app.services import process_scope
from app.services import storage as storage_service

router = APIRouter(prefix="/process-documents", tags=["流程标准文件"])


def _fail(exc: document_service.ProcessDocumentError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _get(db: DbSession, document_id: int) -> ProcessDocument:
    document = db.get(ProcessDocument, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="流程标准文件不存在")
    return document


def _get_version(
    db: DbSession, document: ProcessDocument, version_id: int
) -> ProcessDocumentVersion:
    version = db.get(ProcessDocumentVersion, version_id)
    if version is None or version.document_id != document.id:
        raise HTTPException(status_code=404, detail="标准文件版本不存在")
    return version


# ------------------------------------------------------------------ 文档


@router.get("/meta", response_model=ProcessDocumentMeta, summary="分类 / 状态标签与状态机")
def meta():
    return document_service.meta()


@router.get("", response_model=List[ProcessDocumentOut], summary="流程标准文件清单")
def list_documents(
    db: DbSession,
    process_id: Optional[int] = None,
    node_key: Optional[str] = Query(default=None, description="按活动节点过滤"),
    project_id: Optional[int] = None,
    org_unit_id: Optional[int] = Query(
        default=None, description="按组织范围过滤：集团通用 + 本级 + 上级继承"
    ),
    category: Optional[ProcessDocumentCategory] = None,
    keyword: Optional[str] = None,
    include_ancestors: bool = Query(
        default=False, description="process_id 时是否包含上级流程继承的标准文件"
    ),
    active_only: bool = True,
):
    stmt = (
        select(ProcessDocument)
        .options(
            joinedload(ProcessDocument.process),
            joinedload(ProcessDocument.org_unit),
            selectinload(ProcessDocument.versions),
        )
        .order_by(ProcessDocument.process_id, ProcessDocument.title)
    )
    condition = document_service.visible_conditions(db, org_unit_id)
    if condition is not None:
        stmt = stmt.where(condition)
    if process_id is not None:
        if include_ancestors:
            stmt = stmt.where(
                ProcessDocument.process_id.in_(process_scope.ancestor_ids(db, process_id))
            )
        else:
            stmt = stmt.where(ProcessDocument.process_id == process_id)
    if node_key:
        stmt = stmt.where(ProcessDocument.node_key == node_key)
    if project_id is not None:
        project = db.get(Project, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
        if project.process_id is not None:
            stmt = stmt.where(
                ProcessDocument.process_id.in_(process_scope.ancestor_ids(db, project.process_id))
            )
    if category is not None:
        stmt = stmt.where(ProcessDocument.category == category.value)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                ProcessDocument.title.like(like),
                ProcessDocument.code.like(like),
                ProcessDocument.description.like(like),
            )
        )
    if active_only:
        stmt = stmt.where(ProcessDocument.is_active.is_(True))
    return [document_service.document_out(db, row) for row in db.scalars(stmt).all()]


@router.get(
    "/effective",
    response_model=List[EffectiveDocumentOut],
    summary="按组织 + 流程 + 日期解析有效版本",
)
def effective_documents(
    db: DbSession,
    org_unit_id: int = Query(..., description="按哪个组织的视角解析"),
    process_id: Optional[int] = None,
    category: Optional[ProcessDocumentCategory] = None,
    on_date: Optional[date] = Query(default=None, alias="date"),
):
    try:
        return document_service.effective_documents(
            db,
            org_unit_id,
            process_id=process_id,
            category=category.value if category else None,
            on_date=on_date,
        )
    except document_service.ProcessDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{document_id}", response_model=ProcessDocumentDetail, summary="文档详情与版本历史")
def get_document(document_id: int, db: DbSession):
    return document_service.document_detail(db, _get(db, document_id))


@router.post(
    "",
    response_model=ProcessDocumentOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建标准文件（MANAGER+）",
)
def create_document(payload: ProcessDocumentCreate, db: DbSession, user: ManagerUser):
    try:
        process = document_service.require_process(db, payload.process_id)
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc
    code = payload.code or document_service.next_document_code(db, process.code)
    if db.scalar(select(ProcessDocument).where(ProcessDocument.code == code)):
        raise HTTPException(status_code=409, detail=f"标准文件编码 {code} 已存在")
    data = as_columns(payload.model_dump(exclude={"code"}))
    try:
        document_service.validate_node_key(db, payload.process_id, data.get("node_key"))
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc
    if data.get("org_unit_id") is not None:
        try:
            org_service.require_org(db, data["org_unit_id"])
        except org_service.OrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if (
        data.get("variation_policy") == AssetVariationPolicy.LOCAL_ONLY.value
        and data.get("org_unit_id") is None
    ):
        raise HTTPException(status_code=400, detail="LOCAL_ONLY 必须指定所属组织")
    if data.get("variant_of_document_id") is not None:
        base = db.get(ProcessDocument, data["variant_of_document_id"])
        if base is None:
            raise HTTPException(status_code=400, detail="依据的标准文件不存在")
        try:
            base_version = document_service.validate_variant(db, base, data.get("org_unit_id"))
        except document_service.ProcessDocumentError as exc:
            raise _fail(exc) from exc
        data["variant_base_version_id"] = base_version.id
    data["owner_user_id"], data["owner"] = resolve_owner(
        db, data.get("owner_user_id"), data.get("owner")
    )
    document = document_service.create_document(db, {"code": code, **data})
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_document",
        document.id,
        f"新建标准文件 {code}（{process.code} {process.name}）",
    )
    db.commit()
    db.refresh(document)
    return document_service.document_out(db, document)


@router.patch(
    "/{document_id}", response_model=ProcessDocumentOut, summary="修改标准文件元数据（MANAGER+）"
)
def update_document(
    document_id: int, payload: ProcessDocumentUpdate, db: DbSession, user: ManagerUser
):
    document = _get(db, document_id)
    data = as_columns(payload.model_dump(exclude_unset=True))
    if "node_key" in data:
        try:
            document_service.validate_node_key(db, document.process_id, data["node_key"])
        except document_service.ProcessDocumentError as exc:
            raise _fail(exc) from exc
    if data.get("org_unit_id") is not None:
        try:
            org_service.require_org(db, data["org_unit_id"])
        except org_service.OrgError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    effective_policy = data.get("variation_policy", document.variation_policy)
    target_org = data.get("org_unit_id", document.org_unit_id)
    if effective_policy == AssetVariationPolicy.LOCAL_ONLY.value and target_org is None:
        raise HTTPException(status_code=400, detail="LOCAL_ONLY 必须指定所属组织")
    if data.get("variation_policy") == AssetVariationPolicy.LOCKED.value:
        variants = (
            db.scalar(
                select(func.count())
                .select_from(ProcessDocument)
                .where(ProcessDocument.variant_of_document_id == document.id)
            )
            or 0
        )
        if variants:
            raise HTTPException(
                status_code=409,
                detail=f"已有 {variants} 个本地变体，不能改为锁定策略",
            )
    apply_owner_update(db, data, document.owner)
    for field, value in data.items():
        if value is None and field in {"title", "category", "is_active"}:
            continue
        setattr(document, field, value)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_document",
        document.id,
        f"更新标准文件 {document.code}：{', '.join(sorted(data.keys())) or '（无变更）'}",
    )
    db.commit()
    db.refresh(document)
    return document_service.document_out(db, document)


@router.delete(
    "/{document_id}", response_model=DeleteResult, summary="删除标准文件（无版本时，MANAGER+）"
)
def delete_document(document_id: int, db: DbSession, user: ManagerUser):
    document = _get(db, document_id)
    versions = (
        db.scalar(
            select(func.count())
            .select_from(ProcessDocumentVersion)
            .where(ProcessDocumentVersion.document_id == document.id)
        )
        or 0
    )
    if versions:
        raise HTTPException(
            status_code=409,
            detail=f"文档已有 {versions} 个版本，请停用（is_active=false）而不是删除",
        )
    code = document.code
    audit_service.record(
        db, user, "DELETE", "process_document", document.id, f"删除标准文件 {code}"
    )
    db.delete(document)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 版本


@router.get(
    "/{document_id}/upgrade-impact",
    response_model=DocumentImpactOut,
    summary="上级新版本的影响分析：落后变体与仍固定旧版的项目交付物",
)
def upgrade_impact(document_id: int, db: DbSession):
    document = _get(db, document_id)
    try:
        return document_service.upgrade_impact(db, document)
    except document_service.ProcessDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{document_id}/rebase",
    response_model=ProcessDocumentVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="变体变基到上级新版本（生成草稿，仍需审批，MANAGER+）",
)
def rebase_variant(
    document_id: int,
    payload: DocumentRebaseRequest,
    db: DbSession,
    user: ManagerUser,
):
    document = _get(db, document_id)
    base_version = db.get(ProcessDocumentVersion, payload.base_version_id)
    if base_version is None:
        raise HTTPException(status_code=404, detail="上级版本不存在")
    try:
        version = document_service.rebase_variant(
            db,
            document,
            base_version,
            payload.acknowledge_major,
            user,
            payload.note,
        )
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_document_version",
        version.id,
        f"变体 {document.code} 变基到上级版本 #{base_version.id}，生成草稿 v{version.version_label}",
    )
    version_key = version.storage_key
    try:
        db.commit()
    except Exception:
        db.rollback()
        if version_key:
            storage_service.get_storage().delete(version_key)
        raise
    db.refresh(version)
    return document_service.version_out(db, version)


@router.get(
    "/{document_id}/versions",
    response_model=List[ProcessDocumentVersionOut],
    summary="版本历史",
)
def list_versions(document_id: int, db: DbSession):
    document = _get(db, document_id)
    return [document_service.version_out(db, v) for v in document.versions]


@router.post(
    "/{document_id}/versions/upload",
    response_model=ProcessDocumentVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="上传标准文件版本（MANAGER+，服务端算 SHA-256）",
)
def upload_version(
    document_id: int,
    db: DbSession,
    user: ManagerUser,
    file: UploadFile = File(...),
    version_label: str = Form(...),
    note: Optional[str] = Form(default=None),
    valid_from: Optional[date] = Form(default=None),
    base_version_id: Optional[int] = Form(default=None),
):
    document = _get(db, document_id)
    if not re.fullmatch(r"\d+\.\d+", version_label):
        raise HTTPException(status_code=400, detail="version_label 必须形如 3.2")

    try:
        filename = storage_service.validate_filename(
            file.filename or "", settings.attachment_allowed_extensions
        )
        storage_service.verify_magic(file.file, filename)
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    storage = storage_service.get_storage()
    key = storage_service.build_key(f"process-documents/{document.id}", filename)
    try:
        checksum, size = storage.save(key, file.file, storage_service.max_bytes())
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    data = {
        "version_label": version_label,
        "note": note,
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
        version = document_service.create_version(db, document, data, user, file_meta)
    except document_service.ProcessDocumentError as exc:
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
            "process_document_version",
            version.id,
            f"标准文件 {document.code} 上传 v{version.version_label}"
            f"（{filename}, sha256={checksum[:12]}…）",
        )
        db.commit()
    except Exception:
        db.rollback()
        storage.delete(key)
        raise
    db.refresh(version)
    return document_service.version_out(db, version)


@router.post(
    "/{document_id}/versions/{version_id}/transition",
    response_model=ProcessDocumentVersionOut,
    summary="版本审批流转（MANAGER+）",
)
def transition_version(
    document_id: int,
    version_id: int,
    payload: ProcessDocumentVersionTransition,
    db: DbSession,
    user: ManagerUser,
):
    document = _get(db, document_id)
    version = _get_version(db, document, version_id)
    previous = version.status
    try:
        version = document_service.transition_version(
            db, document, version, payload.status.value, user
        )
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "UPDATE",
        "process_document_version",
        version.id,
        f"标准文件 {document.code} v{version.version_label}：{previous} → {version.status}"
        + (f"（{payload.note}）" if payload.note else ""),
    )
    db.commit()
    db.refresh(version)
    return document_service.version_out(db, version)


@router.get(
    "/{document_id}/versions/{version_id}/download",
    summary="下载标准文件版本（登录即可）",
)
def download_version(document_id: int, version_id: int, db: DbSession, user: CurrentUser):
    document = _get(db, document_id)
    version = _get_version(db, document, version_id)
    if not version.storage_key:
        raise HTTPException(status_code=404, detail="该版本没有上传文件")

    storage = storage_service.get_storage()
    try:
        handle = storage.open(version.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="文件不存在或已被清理") from exc
    except storage_service.StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit_service.record(
        db,
        user,
        "DOWNLOAD",
        "process_document_version",
        version.id,
        f"下载标准文件 {document.code} v{version.version_label}",
    )
    db.commit()

    filename = version.file_name or f"{document.code}-v{version.version_label}"
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


# ------------------------------------------------------------------ 跨域动作


@router.post(
    "/{document_id}/versions/{version_id}/copy-to-deliverable",
    response_model=DeliverableVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="复制标准文件到项目交付物（固定来源版本）",
)
def copy_to_deliverable(
    document_id: int,
    version_id: int,
    payload: DocumentCopyRequest,
    db: DbSession,
    user: WriteUser,
):
    document = _get(db, document_id)
    version = _get_version(db, document, version_id)
    instance = db.get(DeliverableInstance, payload.deliverable_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="交付物实例不存在")
    project = db.get(Project, instance.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    ensure_can_edit_owned(user, project.owner_user_id, project.owner)

    try:
        copied = document_service.copy_to_deliverable(
            db,
            document,
            version,
            instance,
            project,
            user,
            title=payload.title,
            note=payload.note,
        )
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc

    audit_service.record(
        db,
        user,
        "CREATE",
        "deliverable_version",
        copied.id,
        f"{project.code} 交付物 {instance.definition.code} 从标准文件 "
        f"{document.code} v{version.version_label} 复制为 R{copied.version_no}",
    )
    copied_key = copied.storage_key
    try:
        db.commit()
    except Exception:
        db.rollback()
        if copied_key:
            storage_service.get_storage().delete(copied_key)
        raise
    db.refresh(copied)
    return deliverable_service.version_out(copied)


@router.post(
    "/{document_id}/promote",
    response_model=ProcessDocumentVersionOut,
    status_code=status.HTTP_201_CREATED,
    summary="把项目交付物版本晋升为标准文件草稿（MANAGER+）",
)
def promote(
    document_id: int,
    payload: DocumentPromoteRequest,
    db: DbSession,
    user: ManagerUser,
):
    document = _get(db, document_id)
    deliverable_version = db.get(DeliverableVersion, payload.deliverable_version_id)
    if deliverable_version is None:
        raise HTTPException(status_code=404, detail="交付物版本不存在")
    try:
        version = document_service.promote_deliverable(
            db, document, deliverable_version, payload.version_label, user, payload.note
        )
    except document_service.ProcessDocumentError as exc:
        raise _fail(exc) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_document_version",
        version.id,
        f"标准文件 {document.code} 从交付物版本 #{deliverable_version.id} 晋升 v{version.version_label}（草稿）",
    )
    version_key = version.storage_key
    try:
        db.commit()
    except Exception:
        db.rollback()
        if version_key:
            storage_service.get_storage().delete(version_key)
        raise
    db.refresh(version)
    return document_service.version_out(db, version)
