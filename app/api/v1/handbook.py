"""员工手册预览、生成、历史与固定来源读取。"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from starlette.background import BackgroundTask

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.schemas.handbook import HandbookCompileIn, HandbookPreviewIn, HandbookPreviewOut
from app.services import handbook, org_access, storage

router = APIRouter(prefix="/handbooks", tags=["员工手册"])


@router.post("/preview", response_model=HandbookPreviewOut)
def preview_handbook(
    payload: HandbookPreviewIn, request: Request, db: DbSession, user: CurrentUser
):
    return handbook.preview(
        db, payload.scope, payload.subject_id, user, application_url=str(request.base_url)
    )


@router.post("", status_code=201)
def compile_handbook(
    payload: HandbookCompileIn, request: Request, db: DbSession, user: ManagerUser
):
    return handbook.compile(
        db,
        payload.scope,
        payload.subject_id,
        user,
        payload.expected_input_hash,
        application_url=str(request.base_url),
    )


@router.get("")
def list_handbooks(scope: str, subject_id: int, db: DbSession, user: CurrentUser):
    if scope not in {"POSITION", "ROLE"}:
        raise HTTPException(400, "手册主体只支持岗位或治理角色")
    subject = db.get(
        __import__("app.models.org", fromlist=["Position"]).Position
        if scope == "POSITION"
        else __import__("app.models.raci", fromlist=["GovernanceRole"]).GovernanceRole,
        subject_id,
    )
    if subject is None:
        raise HTTPException(404, "手册主体不存在")
    org_access.ensure_visible(db, user, subject.org_unit_id)
    condition = (
        ProcessDocument.position_id == subject_id
        if scope == "POSITION"
        else ProcessDocument.governance_role_id == subject_id
    )
    rows = db.scalars(
        select(ProcessDocumentVersion)
        .join(ProcessDocument)
        .where(
            condition,
            ProcessDocument.scope == scope,
            ProcessDocument.category == "HANDBOOK",
            ProcessDocument.is_active.is_(True),
        )
        .order_by(ProcessDocumentVersion.id.desc())
    ).all()
    return [handbook.get_handbook(db, row.id, user) for row in rows]


@router.get("/source")
def source(version_id: int, document_id: int, db: DbSession, user: CurrentUser):
    document = db.get(ProcessDocument, document_id)
    row = db.get(ProcessDocumentVersion, version_id)
    if document is None or row is None or row.document_id != document.id:
        raise HTTPException(404, "原依据不存在")
    if document.process_id is None:
        raise HTTPException(404, "原依据不属于流程")
    process = db.get(ProcessArch, document.process_id)
    if process is None:
        raise HTTPException(404, "原流程不存在")
    org_access.ensure_visible(db, user, process.org_unit_id)
    if document.org_unit_id is not None:
        org_access.ensure_visible(db, user, document.org_unit_id)
    if not row.storage_key:
        raise HTTPException(404, "原依据没有可打开文件")
    try:
        handle = storage.get_storage().open(row.storage_key)
    except FileNotFoundError as exc:
        raise HTTPException(404, "原依据文件不存在") from exc
    return StreamingResponse(
        handle,
        media_type=row.mime_type or "application/octet-stream",
        background=BackgroundTask(handle.close),
    )


@router.get("/{version_id}")
def get_handbook(version_id: int, db: DbSession, user: CurrentUser):
    return handbook.get_handbook(db, version_id, user)
