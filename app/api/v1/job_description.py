"""岗位责任书：只读预览与岗位产物。"""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.schemas.job_description import (
    JobDescriptionCompileIn,
    JobDescriptionPreviewIn,
    JobDescriptionPreviewOut,
)
from app.services import job_description

router = APIRouter(prefix="/positions", tags=["岗位职责"])


@router.post("/{position_id}/job-description/preview", response_model=JobDescriptionPreviewOut)
def preview_job_description(
    position_id: int,
    payload: JobDescriptionPreviewIn,
    request: Request,
    db: DbSession,
    user: CurrentUser,
):
    return job_description.preview(
        db, position_id, user, payload.period, application_url=str(request.base_url)
    )


@router.post("/{position_id}/job-descriptions", status_code=201)
def compile_job_description(
    position_id: int,
    payload: JobDescriptionCompileIn,
    request: Request,
    db: DbSession,
    user: ManagerUser,
):
    return job_description.compile(
        db,
        position_id,
        user,
        payload.period,
        payload.expected_input_hash,
        application_url=str(request.base_url),
    )


@router.get("/{position_id}/job-descriptions/{version_id}")
def get_job_description(position_id: int, version_id: int, db: DbSession, user: CurrentUser):
    return job_description.get_description(db, position_id, version_id, user)


@router.get("/{position_id}/job-descriptions")
def list_job_descriptions(position_id: int, db: DbSession, user: CurrentUser):
    from sqlalchemy import select

    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.services import position_coverage

    position_coverage.coverage(db, position_id, user)
    versions = db.scalars(
        select(ProcessDocumentVersion)
        .join(ProcessDocument)
        .where(
            ProcessDocument.scope == "POSITION",
            ProcessDocument.position_id == position_id,
            ProcessDocument.category == "JOB_DESCRIPTION",
        )
        .order_by(ProcessDocumentVersion.id.desc())
    ).all()
    return [job_description.get_description(db, position_id, v.id, user) for v in versions]
