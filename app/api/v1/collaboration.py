"""BPMN 元素评论 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, WriteUser
from app.models.enums import Role
from app.schemas.collaboration import CommentCreate, CommentOut
from app.services import audit as audit_service
from app.services import collaboration as comment_service

router = APIRouter(prefix="/processes", tags=["BPMN 协作"])


def _is_manager(user) -> bool:
    return user.role in (Role.ADMIN.value, Role.MANAGER.value)


@router.get(
    "/{process_id}/comments",
    response_model=List[CommentOut],
    summary="流程元素的评论",
)
def list_comments(
    process_id: int,
    db: DbSession,
    user: CurrentUser,
    element_id: Optional[str] = None,
    status_: Optional[str] = Query(default=None, alias="status", pattern="^(OPEN|RESOLVED)$"),
    limit: int = Query(default=200, ge=1, le=500),
):
    try:
        rows = comment_service.list_comments(
            db, process_id, element_id=element_id, status=status_, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [comment_service.comment_out(row) for row in rows]


@router.post(
    "/{process_id}/comments",
    response_model=CommentOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增元素评论",
)
def create_comment(process_id: int, payload: CommentCreate, db: DbSession, user: WriteUser):
    try:
        row = comment_service.create_comment(db, process_id, payload.model_dump(), user)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_comment",
        row.id,
        f"评论流程 {process_id} 元素 {row.element_id}",
    )
    db.commit()
    db.refresh(row)
    return comment_service.comment_out(row)


@router.post(
    "/{process_id}/comments/{comment_id}/resolve",
    response_model=CommentOut,
    summary="解决评论（作者或流程管理科）",
)
def resolve_comment(process_id: int, comment_id: int, db: DbSession, user: CurrentUser):
    from app.models.collaboration import ProcessComment

    row = db.get(ProcessComment, comment_id)
    if row is None or row.process_id != process_id:
        raise HTTPException(status_code=404, detail="评论不存在")
    if not _is_manager(user) and row.author_user_id != user.id:
        raise HTTPException(status_code=403, detail="只有评论作者或流程管理科可以解决")
    comment_service.resolve_comment(db, row, user)
    audit_service.record(db, user, "UPDATE", "process_comment", row.id, f"解决评论 {row.id}")
    db.commit()
    db.refresh(row)
    return comment_service.comment_out(row)
