"""流程知识库：场景匹配、使用证据、求真审核。

知识库只放可参考、可改编的案例 / 模板 / 方法 / 工具指南。
强制执行的制度走 `process_document`；工具定义走 `tool` 表。
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    ensure_can_edit_owned,
)
from app.core.timeutil import utcnow
from app.models.enums import (
    KnowledgeStatus,
    KnowledgeType,
    Methodology,
    ProcessDocumentCategory,
    Role,
)
from app.models.knowledge import (
    KnowledgeItem,
    KnowledgeRecommendLog,
    KnowledgeReview,
    KnowledgeScenario,
    KnowledgeScenarioLink,
    KnowledgeTag,
    KnowledgeUsage,
    KnowledgeWorkflowLink,
)
from app.models.user import User
from app.schemas.common import DeleteResult, Page, as_columns
from app.schemas.knowledge import (
    KnowledgeArchiveCandidateOut,
    KnowledgeBrief,
    KnowledgeCreate,
    KnowledgeEffectStatsOut,
    KnowledgeMetaOut,
    KnowledgeOut,
    KnowledgeReadRequest,
    KnowledgeRecommendLogOut,
    KnowledgeRecommendRequest,
    KnowledgeRecommendResponse,
    KnowledgeReviewOut,
    KnowledgeReviewRequest,
    KnowledgeScenarioCreate,
    KnowledgeScenarioOut,
    KnowledgeScenarioUpdate,
    KnowledgeStandardMigrationOut,
    KnowledgeStandardMigrationRequest,
    KnowledgeStatsOut,
    KnowledgeUpdate,
    KnowledgeUsageCreate,
    KnowledgeUsageOut,
)
from app.services import audit as audit_service
from app.services import knowledge_match
from app.services import process_document as document_service

router = APIRouter(prefix="/knowledge", tags=["流程知识库"])

VISIBLE_STATUSES = {
    KnowledgeStatus.PUBLISHED.value,
    KnowledgeStatus.VERIFIED.value,
}

# 最佳实践晋升门槛：小样本不足以证明有效，必须同时满足次数与有效率
BEST_PRACTICE_MIN_USES = 5
BEST_PRACTICE_MIN_RATE = 0.7


def _is_manager(user: User) -> bool:
    return user.role in (Role.ADMIN.value, Role.MANAGER.value)


def _reject_standard(type_: Optional[KnowledgeType]) -> None:
    if type_ == KnowledgeType.STANDARD:
        raise HTTPException(status_code=400, detail="标准制度请到「交付物与模板库 → 流程标准文件」")


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


def _replace_scenarios(db: DbSession, item: KnowledgeItem, codes: List[str]) -> None:
    """场景整体替换。未知 code 直接拒绝，避免静默丢数据。"""
    wanted = {code for code in (codes or []) if code}
    scenarios = {
        row.code: row
        for row in db.scalars(
            select(KnowledgeScenario).where(KnowledgeScenario.code.in_(wanted))
        ).all()
    }
    unknown = sorted(wanted - set(scenarios))
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知场景：{', '.join(unknown)}")
    for row in list(item.scenario_rows):
        db.delete(row)
    db.flush()
    for code in wanted:
        db.add(KnowledgeScenarioLink(knowledge_id=item.id, scenario_id=scenarios[code].id))


def _replace_workflow_link(
    db: DbSession,
    item: KnowledgeItem,
    stage_no: Optional[int],
    step_no: Optional[str],
) -> None:
    for row in list(item.workflow_links):
        db.delete(row)
    db.flush()
    if stage_no is None and not step_no:
        return
    if stage_no is None:
        raise HTTPException(status_code=400, detail="指定工作流步骤时必须同时指定阶段")
    db.add(
        KnowledgeWorkflowLink(
            knowledge_id=item.id,
            stage_no=stage_no,
            step_no=(step_no or "").strip(),
        )
    )


def _usage_stats(db: DbSession, item: KnowledgeItem):
    return knowledge_match.effectiveness_stats(db, [item.id]).get(item.id, (0, 0, None))


def _usage_out(row: KnowledgeUsage) -> KnowledgeUsageOut:
    return KnowledgeUsageOut(
        id=row.id,
        knowledge_id=row.knowledge_id,
        project_id=row.project_id,
        step_no=row.step_no,
        used_by_user_id=row.used_by_user_id,
        used_by=row.used_by.display_name if row.used_by else None,
        used_at=row.used_at,
        outcome=row.outcome,
        outcome_label=knowledge_match.OUTCOME_LABELS.get(row.outcome, row.outcome),
        note=row.note,
        evidence_url=row.evidence_url,
    )


def _review_out(row: KnowledgeReview) -> KnowledgeReviewOut:
    return KnowledgeReviewOut(
        id=row.id,
        knowledge_id=row.knowledge_id,
        reviewer_user_id=row.reviewer_user_id,
        reviewer=row.reviewer.display_name if row.reviewer else None,
        decision=row.decision,
        decision_label=knowledge_match.REVIEW_DECISION_LABELS.get(row.decision, row.decision),
        from_status=row.from_status,
        from_status_label=knowledge_match.STATUS_LABELS.get(row.from_status, row.from_status),
        to_status=row.to_status,
        to_status_label=knowledge_match.STATUS_LABELS.get(row.to_status, row.to_status),
        note=row.note,
        created_at=row.created_at,
    )


def _recommend_log_out(row: KnowledgeRecommendLog) -> KnowledgeRecommendLogOut:
    return KnowledgeRecommendLogOut(
        id=row.id,
        user_id=row.user_id,
        user=row.user.display_name if row.user else None,
        problem=row.problem,
        scenario_codes=list(row.scenario_codes or []),
        stage_no=row.stage_no,
        step_no=row.step_no,
        result_ids=list(row.result_ids or []),
        created_at=row.created_at,
    )


def _scenario_out(row: KnowledgeScenario) -> KnowledgeScenarioOut:
    return KnowledgeScenarioOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        sort_order=row.sort_order,
        is_active=row.is_active,
    )


def _load_item(db: DbSession, item_id: int) -> KnowledgeItem:
    item = db.scalar(
        select(KnowledgeItem)
        .options(
            selectinload(KnowledgeItem.tag_rows),
            selectinload(KnowledgeItem.scenario_rows).selectinload(KnowledgeScenarioLink.scenario),
            selectinload(KnowledgeItem.workflow_links),
            selectinload(KnowledgeItem.verified_by),
        )
        .where(KnowledgeItem.id == item_id)
    )
    if item is None:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return item


def _assert_can_view(item: KnowledgeItem, user: User) -> None:
    if item.status in VISIBLE_STATUSES:
        return
    if _is_manager(user) or (item.owner_user_id and item.owner_user_id == user.id):
        return
    raise HTTPException(status_code=404, detail="知识条目不存在")


def _base_visible_query(user: User, status_: Optional[KnowledgeStatus]):
    stmt = (
        select(KnowledgeItem)
        .options(
            selectinload(KnowledgeItem.tag_rows),
            selectinload(KnowledgeItem.scenario_rows).selectinload(KnowledgeScenarioLink.scenario),
            selectinload(KnowledgeItem.workflow_links),
            selectinload(KnowledgeItem.verified_by),
        )
        .where(KnowledgeItem.type != KnowledgeType.STANDARD.value)
    )
    if status_ is not None:
        if status_.value not in VISIBLE_STATUSES and not _is_manager(user):
            raise HTTPException(status_code=403, detail="该状态的知识仅流程管理科可查看")
        stmt = stmt.where(KnowledgeItem.status == status_.value)
    else:
        stmt = stmt.where(KnowledgeItem.status.in_(VISIBLE_STATUSES))
    return stmt


def _apply_list_filters(
    stmt,
    scenario: Optional[str],
    stage_no: Optional[int],
    step_no: Optional[str],
    tag: Optional[str],
    keyword: Optional[str],
):
    if scenario:
        stmt = stmt.where(
            KnowledgeItem.scenario_rows.any(
                KnowledgeScenarioLink.scenario.has(KnowledgeScenario.code == scenario)
            )
        )
    if stage_no is not None:
        stmt = stmt.where(
            KnowledgeItem.workflow_links.any(KnowledgeWorkflowLink.stage_no == stage_no)
        )
    if step_no:
        stmt = stmt.where(
            KnowledgeItem.workflow_links.any(KnowledgeWorkflowLink.step_no == step_no)
        )
    if tag:
        stmt = stmt.where(KnowledgeItem.tag_rows.any(KnowledgeTag.tag == tag))
    if keyword:
        # search_text 在写时同步；PostgreSQL 上由 pg_trgm GIN 索引加速 ILIKE，
        # SQLite 退化为普通 LIKE，两套环境行为一致。
        stmt = stmt.where(KnowledgeItem.search_text.ilike(f"%{keyword.strip()}%"))
    return stmt


def _page_of_briefs(db: DbSession, items: List[KnowledgeItem], page: int, size: int):
    ids = [item.id for item in items]
    stats = knowledge_match.effectiveness_stats(db, ids)
    ordered = items[(page - 1) * size : page * size]
    return Page[KnowledgeBrief](
        total=len(items),
        page=page,
        page_size=size,
        items=[
            knowledge_match.to_brief(item, stats.get(item.id, (0, 0, None))) for item in ordered
        ],
    )


# ------------------------------------------------------------------ 场景 / 元数据


@router.get(
    "/scenarios",
    response_model=List[KnowledgeScenarioOut],
    summary="场景字典（按痛点找知识）",
)
def list_scenarios(
    db: DbSession,
    user: CurrentUser,
    include_inactive: bool = Query(default=False),
):
    if include_inactive and not _is_manager(user):
        raise HTTPException(status_code=403, detail="只有流程管理科可以查看停用场景")
    return knowledge_match.scenario_list(db, include_inactive=include_inactive)


@router.post(
    "/scenarios",
    response_model=KnowledgeScenarioOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增场景（Manager）",
)
def create_scenario(payload: KnowledgeScenarioCreate, db: DbSession, user: ManagerUser):
    exists = db.scalar(
        select(KnowledgeScenario).where(KnowledgeScenario.code == payload.code.upper())
    )
    if exists is not None:
        raise HTTPException(status_code=409, detail=f"场景编码 {payload.code} 已存在")
    row = KnowledgeScenario(**payload.model_dump())
    row.code = row.code.upper()
    db.add(row)
    db.flush()
    audit_service.record(db, user, "CREATE", "knowledge_scenario", row.id, f"新增场景 {row.code}")
    db.commit()
    db.refresh(row)
    return _scenario_out(row)


@router.patch(
    "/scenarios/{scenario_id}",
    response_model=KnowledgeScenarioOut,
    summary="修改/停用场景（Manager）",
)
def update_scenario(
    scenario_id: int,
    payload: KnowledgeScenarioUpdate,
    db: DbSession,
    user: ManagerUser,
):
    row = db.get(KnowledgeScenario, scenario_id)
    if row is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    audit_service.record(db, user, "UPDATE", "knowledge_scenario", row.id, f"更新场景 {row.code}")
    db.commit()
    db.refresh(row)
    return _scenario_out(row)


@router.get("/meta", response_model=KnowledgeMetaOut, summary="知识库标签与统计")
def knowledge_meta(db: DbSession):
    items = db.scalars(
        select(KnowledgeItem).where(KnowledgeItem.type != KnowledgeType.STANDARD.value)
    ).all()
    today = date.today()
    stats = KnowledgeStatsOut(
        total=sum(1 for item in items if item.status in VISIBLE_STATUSES),
        verified=sum(1 for item in items if item.status == KnowledgeStatus.VERIFIED.value),
        published=sum(1 for item in items if item.status == KnowledgeStatus.PUBLISHED.value),
        pending_review=sum(1 for item in items if item.status == KnowledgeStatus.IN_REVIEW.value),
        review_overdue=sum(
            1
            for item in items
            if item.status in VISIBLE_STATUSES
            and (
                (item.review_due_at is not None and item.review_due_at < today)
                or (item.review_due_at is None and item.last_verified_at is None)
            )
        ),
        archived=sum(1 for item in items if item.status == KnowledgeStatus.ARCHIVED.value),
        best_practice=sum(1 for item in items if item.is_best_practice),
    )
    return KnowledgeMetaOut(
        type_labels=knowledge_match.TYPE_LABELS,
        status_labels=knowledge_match.STATUS_LABELS,
        outcome_labels=knowledge_match.OUTCOME_LABELS,
        stats=stats.model_dump(),
        scenarios=knowledge_match.scenario_list(db),
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


@router.get(
    "/effect-stats",
    response_model=KnowledgeEffectStatsOut,
    summary="全局使用效果统计（运营面板）",
)
def get_effect_stats(db: DbSession, user: ManagerUser):
    return knowledge_match.effect_stats(db)


@router.get(
    "/archive-candidates",
    response_model=List[KnowledgeArchiveCandidateOut],
    summary="归档候选（长期未使用的公开知识）",
)
def list_archive_candidates(
    db: DbSession,
    user: ManagerUser,
    months: int = Query(default=12, ge=1, le=60),
    limit: int = Query(default=50, ge=1, le=200),
):
    return knowledge_match.archive_candidates(db, months=months, limit=limit)


@router.get(
    "/recommend-logs",
    response_model=List[KnowledgeRecommendLogOut],
    summary="推荐解释日志（Manager）",
)
def list_recommend_logs(
    db: DbSession,
    user: ManagerUser,
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = db.scalars(
        select(KnowledgeRecommendLog)
        .options(selectinload(KnowledgeRecommendLog.user))
        .order_by(KnowledgeRecommendLog.created_at.desc(), KnowledgeRecommendLog.id.desc())
        .limit(limit)
    ).all()
    return [_recommend_log_out(row) for row in rows]


@router.get(
    "/standard-candidates",
    response_model=List[KnowledgeBrief],
    summary="待迁移到制度中心的旧制度知识（Manager）",
)
def list_standard_candidates(db: DbSession, user: ManagerUser):
    rows = db.scalars(
        select(KnowledgeItem)
        .options(
            selectinload(KnowledgeItem.tag_rows),
            selectinload(KnowledgeItem.scenario_rows).selectinload(KnowledgeScenarioLink.scenario),
            selectinload(KnowledgeItem.workflow_links),
        )
        .where(
            KnowledgeItem.type == KnowledgeType.STANDARD.value,
            KnowledgeItem.status == KnowledgeStatus.ARCHIVED.value,
        )
        .order_by(KnowledgeItem.id)
    ).all()
    stats = knowledge_match.effectiveness_stats(db, [row.id for row in rows])
    return [knowledge_match.to_brief(row, stats.get(row.id, (0, 0, None))) for row in rows]


@router.post(
    "/recommend",
    response_model=KnowledgeRecommendResponse,
    summary="按场景/问题推荐知识",
)
def recommend_knowledge(payload: KnowledgeRecommendRequest, db: DbSession, user: CurrentUser):
    items = knowledge_match.recommend(
        db,
        problem=payload.problem,
        scenario_codes=payload.scenario_codes,
        stage_no=payload.stage_no,
        step_no=payload.step_no,
        limit=payload.limit,
    )
    # 推荐解释留痕：问题、上下文与返回的条目 id，便于事后审计“为什么推了这条”
    db.add(
        KnowledgeRecommendLog(
            user_id=user.id,
            problem=payload.problem,
            scenario_codes=payload.scenario_codes,
            stage_no=payload.stage_no,
            step_no=payload.step_no,
            result_ids=[item.id for item in items],
        )
    )
    db.commit()
    return KnowledgeRecommendResponse(
        problem=payload.problem,
        scenario_codes=payload.scenario_codes,
        items=items,
        hint=knowledge_match.HINT,
    )


# ------------------------------------------------------------------ 列表 / 新建


@router.get("", response_model=Page[KnowledgeBrief], summary="知识库检索")
def list_knowledge(
    db: DbSession,
    user: CurrentUser,
    type_: Optional[KnowledgeType] = Query(default=None, alias="type"),
    methodology: Optional[Methodology] = None,
    tool_code: Optional[str] = None,
    tag: Optional[str] = None,
    keyword: Optional[str] = None,
    scenario: Optional[str] = None,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
    step_no: Optional[str] = None,
    status_: Optional[KnowledgeStatus] = Query(default=None, alias="status"),
    sort: str = Query(default="recent", pattern="^(recent|hot|effect|match)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
):
    stmt = _base_visible_query(user, status_)
    if type_ is not None:
        if type_ == KnowledgeType.STANDARD:
            raise HTTPException(
                status_code=400, detail="标准制度请到「交付物与模板库 → 流程标准文件」"
            )
        stmt = stmt.where(KnowledgeItem.type == type_.value)
    if methodology is not None:
        stmt = stmt.where(KnowledgeItem.methodology == methodology.value)
    if tool_code:
        stmt = stmt.where(KnowledgeItem.tool_code == tool_code)
    stmt = _apply_list_filters(stmt, scenario, stage_no, step_no, tag, keyword)

    if sort in ("effect", "match"):
        # 当前数据量适合在内存里按证据/匹配度排序；分页仍然返回稳定的 total。
        candidates = list(db.scalars(stmt.limit(500)).all())
        if sort == "match" and (keyword or scenario or stage_no or step_no):
            recommended = knowledge_match.recommend(
                db,
                problem=keyword,
                scenario_codes=[scenario] if scenario else [],
                stage_no=stage_no,
                step_no=step_no,
                limit=500,
            )
            allowed = {item.id for item in candidates}
            rank = {row.id: index for index, row in enumerate(recommended) if row.id in allowed}
            candidates = [item for item in candidates if item.id in rank]
            candidates.sort(key=lambda item: rank[item.id])
        else:
            stats = knowledge_match.effectiveness_stats(db, [item.id for item in candidates])
            candidates.sort(
                key=lambda item: (
                    -(stats.get(item.id, (0, 0, None))[2] or 0),
                    -int(item.is_best_practice),
                    item.title,
                )
            )
        return _page_of_briefs(db, candidates, page, page_size)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (
        KnowledgeItem.download_count.desc() if sort == "hot" else KnowledgeItem.updated_at.desc()
    )
    rows = db.scalars(
        stmt.order_by(order, KnowledgeItem.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    stats = knowledge_match.effectiveness_stats(db, [row.id for row in rows])
    return Page[KnowledgeBrief](
        total=total,
        page=page,
        page_size=page_size,
        items=[knowledge_match.to_brief(row, stats.get(row.id, (0, 0, None))) for row in rows],
    )


@router.post(
    "", response_model=KnowledgeOut, status_code=status.HTTP_201_CREATED, summary="新增知识草稿"
)
def create_knowledge(payload: KnowledgeCreate, db: DbSession, user: WriteUser):
    _reject_standard(payload.type)
    data = as_columns(payload.model_dump(exclude={"tags", "scenario_codes", "stage_no", "step_no"}))
    data["status"] = KnowledgeStatus.DRAFT.value
    data["owner_user_id"] = payload.owner_user_id or user.id
    data["author"] = payload.author or user.display_name
    obj = KnowledgeItem(**data)
    db.add(obj)
    db.flush()
    _replace_tags(db, obj, payload.tags)
    _replace_scenarios(db, obj, payload.scenario_codes)
    _replace_workflow_link(db, obj, payload.stage_no, payload.step_no)
    audit_service.record(db, user, "CREATE", "knowledge", obj.id, f"新增知识草稿《{obj.title}》")
    db.commit()
    obj = _load_item(db, obj.id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


# ------------------------------------------------------------------ 详情 / 更新 / 删除


@router.get("/{item_id}", response_model=KnowledgeOut, summary="知识条目详情")
def get_knowledge(item_id: int, db: DbSession, user: CurrentUser):
    obj = _load_item(db, item_id)
    _assert_can_view(obj, user)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.get(
    "/{item_id}/usage",
    response_model=List[KnowledgeUsageOut],
    summary="知识的使用证据",
)
def list_usage(item_id: int, db: DbSession, user: CurrentUser):
    obj = _load_item(db, item_id)
    _assert_can_view(obj, user)
    rows = db.scalars(
        select(KnowledgeUsage)
        .options(selectinload(KnowledgeUsage.used_by))
        .where(KnowledgeUsage.knowledge_id == item_id)
        .order_by(KnowledgeUsage.used_at.desc(), KnowledgeUsage.id.desc())
        .limit(50)
    ).all()
    return [_usage_out(row) for row in rows]


@router.patch("/{item_id}", response_model=KnowledgeOut, summary="更新知识条目")
def update_knowledge(item_id: int, payload: KnowledgeUpdate, db: DbSession, user: WriteUser):
    _reject_standard(payload.type)
    obj = _load_item(db, item_id)
    ensure_can_edit_owned(user, obj.owner_user_id, obj.author)

    data = payload.model_dump(exclude_unset=True)
    tags = data.pop("tags", None)
    scenario_codes = data.pop("scenario_codes", None)
    stage_no = data.pop("stage_no", None)
    step_no = data.pop("step_no", None)
    for field, value in as_columns(data).items():
        setattr(obj, field, value)
    if tags is not None:
        _replace_tags(db, obj, tags)
    if scenario_codes is not None:
        _replace_scenarios(db, obj, scenario_codes)
    if "stage_no" in payload.model_fields_set or "step_no" in payload.model_fields_set:
        _replace_workflow_link(db, obj, stage_no, step_no)

    # 内容变更后旧验证结论不再成立，退回「待复核」
    if obj.status == KnowledgeStatus.VERIFIED.value:
        obj.status = KnowledgeStatus.PUBLISHED.value
        obj.last_verified_at = None
        obj.review_due_at = None
        obj.verified_by_user_id = None
    obj.version = (obj.version or 1) + 1
    audit_service.record(
        db,
        user,
        "UPDATE",
        "knowledge",
        obj.id,
        f"更新知识条目《{obj.title}》到 v{obj.version}",
    )
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.delete("/{item_id}", response_model=DeleteResult, summary="删除知识条目")
def delete_knowledge(item_id: int, db: DbSession, user: ManagerUser):
    obj = _load_item(db, item_id)
    audit_service.record(db, user, "DELETE", "knowledge", obj.id, f"删除知识条目《{obj.title}》")
    db.delete(obj)
    db.commit()
    return DeleteResult(deleted=1)


# ------------------------------------------------------------------ 使用证据 / 审核


@router.post(
    "/{item_id}/usage",
    response_model=KnowledgeUsageOut,
    status_code=status.HTTP_201_CREATED,
    summary="记录一次使用证据",
)
def record_usage(item_id: int, payload: KnowledgeUsageCreate, db: DbSession, user: WriteUser):
    obj = _load_item(db, item_id)
    _assert_can_view(obj, user)

    # 短期去重：同一人、同一条目、同一项目/步骤、同一效果，10 分钟内只记一次，
    # 避免重复点击或刷新把证据刷高。
    step_no = (payload.step_no or "").strip() or None
    recent = utcnow() - timedelta(minutes=10)
    conditions = [
        KnowledgeUsage.knowledge_id == item_id,
        KnowledgeUsage.used_by_user_id == user.id,
        KnowledgeUsage.outcome == payload.outcome,
        KnowledgeUsage.used_at >= recent,
    ]
    if payload.project_id is None:
        conditions.append(KnowledgeUsage.project_id.is_(None))
    else:
        conditions.append(KnowledgeUsage.project_id == payload.project_id)
    if step_no is None:
        conditions.append(KnowledgeUsage.step_no.is_(None))
    else:
        conditions.append(KnowledgeUsage.step_no == step_no)
    duplicate = db.scalar(
        select(KnowledgeUsage)
        .options(selectinload(KnowledgeUsage.used_by))
        .where(*conditions)
        .order_by(KnowledgeUsage.used_at.desc())
        .limit(1)
    )
    if duplicate is not None:
        return _usage_out(duplicate)

    row = KnowledgeUsage(
        knowledge_id=item_id,
        project_id=payload.project_id,
        step_no=step_no,
        used_by_user_id=user.id,
        used_at=utcnow(),
        outcome=payload.outcome,
        note=payload.note,
        evidence_url=payload.evidence_url,
    )
    db.add(row)
    db.flush()
    audit_service.record(
        db,
        user,
        "CREATE",
        "knowledge_usage",
        row.id,
        f"记录知识《{obj.title}》使用证据：{knowledge_match.OUTCOME_LABELS.get(payload.outcome)}",
    )
    db.commit()
    db.refresh(row)
    row = db.scalar(
        select(KnowledgeUsage)
        .options(selectinload(KnowledgeUsage.used_by))
        .where(KnowledgeUsage.id == row.id)
    )
    return _usage_out(row)


@router.post("/{item_id}/submit", response_model=KnowledgeOut, summary="提交求真审核")
def submit_review(item_id: int, db: DbSession, user: WriteUser):
    obj = _load_item(db, item_id)
    ensure_can_edit_owned(user, obj.owner_user_id, obj.author)
    if obj.status == KnowledgeStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="该条目已在审核中")
    if obj.status == KnowledgeStatus.VERIFIED.value:
        raise HTTPException(status_code=409, detail="该条目已验证通过，无需重复提交")

    used, _effective, _rate = _usage_stats(db, obj)
    missing = []
    if not (obj.claim or "").strip():
        missing.append("主张")
    if not (obj.applicable_when or "").strip():
        missing.append("适用条件")
    if not (obj.not_applicable_when or "").strip():
        missing.append("不适用/反证条件")
    if not (obj.evidence_summary or "").strip() and used == 0:
        missing.append("使用证据")
    if not obj.owner_user_id:
        missing.append("维护人")
    if not obj.scenario_rows:
        missing.append("适用场景")
    if missing:
        raise HTTPException(status_code=400, detail="提交审核前请补齐：" + "、".join(missing))

    obj.status = KnowledgeStatus.IN_REVIEW.value
    audit_service.record(
        db, user, "UPDATE", "knowledge", obj.id, f"提交知识《{obj.title}》求真审核"
    )
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.post("/{item_id}/review", response_model=KnowledgeOut, summary="审核知识条目")
def review_knowledge(
    item_id: int, payload: KnowledgeReviewRequest, db: DbSession, user: ManagerUser
):
    obj = _load_item(db, item_id)
    if obj.status != KnowledgeStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="只有待审核的条目可以审核")
    previous_status = obj.status
    if payload.decision == "APPROVE":
        obj.status = KnowledgeStatus.VERIFIED.value
        obj.last_verified_at = utcnow()
        obj.review_due_at = date.today() + timedelta(days=365)
        obj.verified_by_user_id = user.id
        action = "通过"
    else:
        obj.status = KnowledgeStatus.DRAFT.value
        action = "驳回"
    db.add(
        KnowledgeReview(
            knowledge_id=obj.id,
            reviewer_user_id=user.id,
            decision=payload.decision,
            from_status=previous_status,
            to_status=obj.status,
            note=payload.note,
        )
    )
    audit_service.record(
        db,
        user,
        "UPDATE",
        "knowledge",
        obj.id,
        f"{action}知识《{obj.title}》审核" + (f"：{payload.note}" if payload.note else ""),
    )
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.get(
    "/{item_id}/reviews",
    response_model=List[KnowledgeReviewOut],
    summary="知识的求真审核历史",
)
def list_reviews(item_id: int, db: DbSession, user: CurrentUser):
    obj = _load_item(db, item_id)
    _assert_can_view(obj, user)
    rows = db.scalars(
        select(KnowledgeReview)
        .options(selectinload(KnowledgeReview.reviewer))
        .where(KnowledgeReview.knowledge_id == item_id)
        .order_by(KnowledgeReview.created_at.desc(), KnowledgeReview.id.desc())
        .limit(100)
    ).all()
    return [_review_out(row) for row in rows]


@router.post("/{item_id}/promote", response_model=KnowledgeOut, summary="晋升为最佳实践（Manager）")
def promote_knowledge(item_id: int, db: DbSession, user: ManagerUser):
    obj = _load_item(db, item_id)
    if obj.status != KnowledgeStatus.VERIFIED.value:
        raise HTTPException(status_code=409, detail="只有已验证的条目可以晋升为最佳实践")
    if obj.is_best_practice:
        raise HTTPException(status_code=409, detail="该条目已经是最佳实践")

    used, effective, _rate = _usage_stats(db, obj)
    rate = effective / used if used else 0.0
    if used < BEST_PRACTICE_MIN_USES or rate < BEST_PRACTICE_MIN_RATE:
        raise HTTPException(
            status_code=400,
            detail=(
                "晋升需要至少使用 "
                f"{BEST_PRACTICE_MIN_USES} 次且有效率 ≥ {int(BEST_PRACTICE_MIN_RATE * 100)}%，"
                f"当前 {used} 次 / {rate:.0%}"
            ),
        )

    obj.is_best_practice = True
    obj.promoted_at = utcnow()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "knowledge",
        obj.id,
        f"晋升知识《{obj.title}》为最佳实践（{used} 次使用 / 有效率 {rate:.0%}）",
    )
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.post("/{item_id}/archive", response_model=KnowledgeOut, summary="归档知识条目")
def archive_knowledge(item_id: int, db: DbSession, user: ManagerUser):
    """归档后不再进入列表/推荐；证据与版本保留，便于追溯。"""
    obj = _load_item(db, item_id)
    if obj.status == KnowledgeStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="该条目已归档")
    obj.status = KnowledgeStatus.ARCHIVED.value
    audit_service.record(db, user, "UPDATE", "knowledge", obj.id, f"归档知识《{obj.title}》")
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))


@router.post(
    "/{item_id}/migrate-to-document",
    response_model=KnowledgeStandardMigrationOut,
    status_code=status.HTTP_201_CREATED,
    summary="把归档的旧制度知识迁移为流程标准文件（Manager）",
)
def migrate_standard_to_document(
    item_id: int,
    payload: KnowledgeStandardMigrationRequest,
    db: DbSession,
    user: ManagerUser,
):
    obj = _load_item(db, item_id)
    if obj.type != KnowledgeType.STANDARD.value or obj.status != KnowledgeStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="只有已归档的 STANDARD 知识可以迁移到制度中心")
    try:
        category = ProcessDocumentCategory(payload.category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"未知制度类型：{payload.category}") from exc
    try:
        process = document_service.require_process(db, payload.process_id)
        document_service.validate_node_key(db, payload.process_id, payload.node_key)
    except document_service.ProcessDocumentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    code = document_service.next_document_code(db, process.code)
    document = document_service.create_document(
        db,
        {
            "process_id": payload.process_id,
            "node_key": payload.node_key,
            "code": code,
            "title": payload.title or obj.title,
            "category": category.value,
            "description": payload.description or obj.content,
            "owner": payload.owner or obj.author,
            "owner_user_id": obj.owner_user_id,
            "org_unit_id": payload.org_unit_id,
            "variation_policy": "PARAMETERIZED",
        },
    )
    version = document_service.create_version(
        db,
        document,
        {
            "version_label": "1.0",
            "note": f"从知识库条目 #{obj.id}《{obj.title}》迁移",
        },
        user,
    )
    audit_service.record(
        db,
        user,
        "CREATE",
        "process_document",
        document.id,
        f"从知识条目 {obj.id} 迁移制度 {document.code}",
    )
    db.commit()
    return KnowledgeStandardMigrationOut(
        knowledge_id=obj.id,
        document_id=document.id,
        document_code=document.code,
        version_id=version.id,
        version_label=version.version_label,
    )


@router.post("/{item_id}/read", response_model=KnowledgeOut, summary="记录一次查阅/下载")
def mark_read(item_id: int, payload: KnowledgeReadRequest, db: DbSession, user: CurrentUser):
    obj = _load_item(db, item_id)
    _assert_can_view(obj, user)
    obj.download_count = (obj.download_count or 0) + payload.increment
    db.commit()
    obj = _load_item(db, item_id)
    return knowledge_match.to_out(obj, _usage_stats(db, obj))
