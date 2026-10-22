"""架构草图：独立 draw.io 白板，不与 BPMN 设计器/执行引擎耦合。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import joinedload

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser
from app.core.config import settings
from app.models.process import ProcessArch
from app.models.project import Project
from app.models.sketch import Sketch
from app.schemas.common import DeleteResult
from app.schemas.sketch import (
    SketchCreate,
    SketchMeta,
    SketchOut,
    SketchSummaryOut,
    SketchUpdate,
)
from app.services import audit as audit_service

router = APIRouter(prefix="/sketches", tags=["架构草图"])


def _summary(row: Sketch) -> SketchSummaryOut:
    return SketchSummaryOut(
        id=row.id,
        title=row.title,
        description=row.description,
        process_id=row.process_id,
        process_code=row.process.code if row.process else None,
        process_name=row.process.name if row.process else None,
        project_id=row.project_id,
        project_code=row.project.code if row.project else None,
        project_name=row.project.name if row.project else None,
        created_by_name=row.created_by_name,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _full(row: Sketch) -> SketchOut:
    return SketchOut(**_summary(row).model_dump(), mxfile_xml=row.mxfile_xml or "")


def _load(db: DbSession, sketch_id: int) -> Sketch:
    row = db.scalar(
        select(Sketch)
        .options(joinedload(Sketch.process), joinedload(Sketch.project))
        .where(Sketch.id == sketch_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="草图不存在")
    return row


def _validate_scope(db: DbSession, process_id: Optional[int], project_id: Optional[int]) -> None:
    if process_id is not None and db.get(ProcessArch, process_id) is None:
        raise HTTPException(status_code=400, detail="关联流程不存在")
    if project_id is not None and db.get(Project, project_id) is None:
        raise HTTPException(status_code=400, detail="关联项目不存在")


@router.get("/meta", response_model=SketchMeta, summary="草图编辑器配置")
def sketch_meta(user: CurrentUser):
    return SketchMeta(embed_url=settings.drawio_embed_url)


@router.get("", response_model=List[SketchSummaryOut], summary="草图列表")
def list_sketches(
    db: DbSession,
    user: CurrentUser,
    keyword: Optional[str] = None,
    process_id: Optional[int] = None,
    project_id: Optional[int] = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    stmt = select(Sketch).options(joinedload(Sketch.process), joinedload(Sketch.project))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(or_(Sketch.title.like(like), Sketch.description.like(like)))
    if process_id is not None:
        stmt = stmt.where(Sketch.process_id == process_id)
    if project_id is not None:
        stmt = stmt.where(Sketch.project_id == project_id)
    rows = db.scalars(stmt.order_by(Sketch.updated_at.desc(), Sketch.id.desc()).limit(limit)).all()
    return [_summary(row) for row in rows]


@router.post(
    "",
    response_model=SketchOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建草图（OWNER+）",
)
def create_sketch(payload: SketchCreate, db: DbSession, user: WriteUser):
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    _validate_scope(db, payload.process_id, payload.project_id)
    row = Sketch(
        title=title,
        description=(payload.description or "").strip() or None,
        process_id=payload.process_id,
        project_id=payload.project_id,
        mxfile_xml=payload.mxfile_xml or "",
        created_by_id=user.id,
        created_by_name=user.display_name,
    )
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "sketch", row.id, f"新建架构草图 {row.title}")
    db.commit()
    return _full(_load(db, row.id))


@router.get("/{sketch_id}", response_model=SketchOut, summary="草图详情（含 mxfile XML）")
def get_sketch(sketch_id: int, db: DbSession, user: CurrentUser):
    return _full(_load(db, sketch_id))


@router.patch(
    "/{sketch_id}",
    response_model=SketchOut,
    summary="修改草图信息 / 保存 draw.io XML（OWNER+）",
)
def update_sketch(
    sketch_id: int,
    payload: SketchUpdate,
    db: DbSession,
    user: WriteUser,
):
    row = _load(db, sketch_id)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data:
        title = (data["title"] or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="标题不能为空")
        data["title"] = title
    if "description" in data:
        data["description"] = (data["description"] or "").strip() or None
    if "process_id" in data or "project_id" in data:
        _validate_scope(
            db,
            data.get("process_id", row.process_id),
            data.get("project_id", row.project_id),
        )
    for key, value in data.items():
        setattr(row, key, value)
    audit_service.record(db, user, "UPDATE", "sketch", row.id, f"保存架构草图 {row.title}")
    db.commit()
    return _full(_load(db, sketch_id))


@router.delete(
    "/{sketch_id}",
    response_model=DeleteResult,
    summary="删除草图（MANAGER+）",
)
def delete_sketch(sketch_id: int, db: DbSession, user: ManagerUser):
    row = _load(db, sketch_id)
    title = row.title
    audit_service.record(db, user, "DELETE", "sketch", row.id, f"删除架构草图 {title}")
    db.delete(row)
    db.commit()
    return DeleteResult(deleted=1)
