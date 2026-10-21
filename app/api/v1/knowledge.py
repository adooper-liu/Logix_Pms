"""流程知识库：案例 / 模板 / 最佳实践 / 标准制度。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession, ManagerUser
from app.models.enums import KnowledgeType, Methodology
from app.models.knowledge import KnowledgeItem, KnowledgeTag
from app.schemas.common import DeleteResult, Page, as_columns
from app.schemas.knowledge import (
    KnowledgeBrief,
    KnowledgeCreate,
    KnowledgeOut,
    KnowledgeReadRequest,
    KnowledgeUpdate,
)
from app.services import audit as audit_service

router = APIRouter(prefix="/knowledge", tags=["流程知识库"])


def _replace_tags(db: DbSession, item: KnowledgeItem, tags: List[str]) -> None:
    """标签整体替换：先清后建，保持与提交内容一致。"""
    for row in list(item.tag_rows):
        db.delete(row)
    db.flush()
    seen = set()
    for raw in tags:
        tag = (raw or "").strip()
        if not tag or tag in seen:
            continue
        seen.add(tag)
        db.add(KnowledgeTag(knowledge_id=item.id, tag=tag))


@router.get("", response_model=Page[KnowledgeBrief], summary="知识库检索")
def list_knowledge(
    db: DbSession,
    type_: Optional[KnowledgeType] = Query(default=None, alias="type"),
    methodology: Optional[Methodology] = None,
    tool_code: Optional[str] = None,
    tag: Optional[str] = None,
    keyword: Optional[str] = None,
    sort: str = Query(default="recent", pattern="^(recent|hot)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = select(KnowledgeItem)
    if type_ is not None:
        stmt = stmt.where(KnowledgeItem.type == type_.value)
    if methodology is not None:
        stmt = stmt.where(KnowledgeItem.methodology == methodology.value)
    if tool_code:
        stmt = stmt.where(KnowledgeItem.tool_code == tool_code)
    if tag:
        # 标签已规范化成关联表，筛选和计数都在 SQL 层完成，
        # total 不再受 page_size 影响
        stmt = stmt.where(KnowledgeItem.tag_rows.any(KnowledgeTag.tag == tag))
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                KnowledgeItem.title.like(like),
                KnowledgeItem.summary.like(like),
                KnowledgeItem.content.like(like),
            )
        )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (
        KnowledgeItem.download_count.desc() if sort == "hot" else KnowledgeItem.created_at.desc()
    )
    rows = db.scalars(
        stmt.options(selectinload(KnowledgeItem.tag_rows))
        .order_by(order, KnowledgeItem.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return Page[KnowledgeBrief](
        total=total,
        page=page,
        page_size=page_size,
        items=[KnowledgeBrief.model_validate(r) for r in rows],
    )


@router.get("/meta/tags", summary="标签云（用于知识库筛选栏）")
def list_tags(db: DbSession, limit: int = Query(default=40, ge=1, le=200)):
    rows = db.execute(
        select(KnowledgeTag.tag, func.count(KnowledgeTag.id).label("n"))
        .group_by(KnowledgeTag.tag)
        .order_by(func.count(KnowledgeTag.id).desc(), KnowledgeTag.tag)
        .limit(limit)
    ).all()
    return {"tags": [{"tag": tag, "count": n} for tag, n in rows]}


@router.get("/{item_id}", response_model=KnowledgeOut, summary="知识条目详情")
def get_knowledge(item_id: int, db: DbSession):
    obj = db.get(KnowledgeItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return KnowledgeOut.model_validate(obj)


@router.post(
    "", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED, summary="新增知识条目"
)
def create_knowledge(payload: KnowledgeCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump(exclude={"tags"}))
    obj = KnowledgeItem(**data)
    db.add(obj)
    db.flush()
    _replace_tags(db, obj, payload.tags)
    audit_service.record(db, user, "CREATE", "knowledge", obj.id, f"新增知识条目《{obj.title}》")
    db.commit()
    db.refresh(obj)
    return KnowledgeOut.model_validate(obj)


@router.patch("/{item_id}", response_model=KnowledgeOut, summary="更新知识条目")
def update_knowledge(item_id: int, payload: KnowledgeUpdate, db: DbSession, user: ManagerUser):
    obj = db.get(KnowledgeItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")

    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    for field, value in as_columns(data).items():
        setattr(obj, field, value)
    if tags is not None:
        _replace_tags(db, obj, tags)
    audit_service.record(db, user, "UPDATE", "knowledge", obj.id, f"更新知识条目《{obj.title}》")
    db.commit()
    db.refresh(obj)
    return KnowledgeOut.model_validate(obj)


@router.post("/{item_id}/read", response_model=KnowledgeOut, summary="记录一次查阅/下载")
def mark_read(item_id: int, payload: KnowledgeReadRequest, db: DbSession):
    obj = db.get(KnowledgeItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    obj.download_count = (obj.download_count or 0) + payload.increment
    db.commit()
    db.refresh(obj)
    return KnowledgeOut.model_validate(obj)


@router.delete("/{item_id}", response_model=DeleteResult, summary="删除知识条目")
def delete_knowledge(item_id: int, db: DbSession, user: ManagerUser):
    obj = db.get(KnowledgeItem, item_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    audit_service.record(db, user, "DELETE", "knowledge", obj.id, f"删除知识条目《{obj.title}》")
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=1)
