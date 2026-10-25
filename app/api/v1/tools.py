"""方法论工具箱：问题驱动匹配、工具清单与详情。"""

from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUser,
    DbSession,
    ManagerUser,
    WriteUser,
    ensure_can_edit_owned,
)
from app.core.timeutil import utcnow
from app.models.deliverable import StepContract
from app.models.enums import KnowledgeStatus, Role, ToolCategory, ToolLevel, ToolStatus
from app.models.knowledge import KnowledgeItem, KnowledgeScenario, KnowledgeScenarioLink
from app.models.project import WorkflowTemplate
from app.models.tool import Tool, ToolScenarioLink, ToolUsage
from app.schemas.common import as_columns
from app.schemas.tool import (
    ToolBrief,
    ToolCategoryGroup,
    ToolCreate,
    ToolDetailOut,
    ToolMatchRequest,
    ToolMatchResponse,
    ToolMetaOut,
    ToolOut,
    ToolReviewRequest,
    ToolUpdate,
    ToolUsageCreate,
    ToolUsageOut,
    ToolUsageSummary,
    ToolWorkflowStepOut,
)
from app.services import audit as audit_service
from app.services import knowledge_match, tool_match

router = APIRouter(prefix="/tools", tags=["方法论工具箱"])

CATEGORY_LABELS = {
    ToolCategory.DIAGNOSE.value: "诊断工具",
    ToolCategory.DESIGN.value: "设计工具",
    ToolCategory.DEPLOY.value: "落地工具",
    ToolCategory.MONITOR.value: "监控工具",
}

TOOL_LEVEL_LABELS = {
    ToolLevel.REQUIRED.value: "必需",
    ToolLevel.RECOMMENDED.value: "推荐",
    ToolLevel.OPTIONAL.value: "可选",
}

DIFFICULTY_LABELS = {
    "LOW": "低",
    "MEDIUM": "中",
    "HIGH": "高",
}

VISIBLE_KNOWLEDGE = {
    KnowledgeStatus.PUBLISHED.value,
    KnowledgeStatus.VERIFIED.value,
}

VISIBLE_TOOL_STATUSES = {ToolStatus.PUBLISHED.value, ToolStatus.VERIFIED.value}


def _is_manager(user) -> bool:
    return user.role in (Role.ADMIN.value, Role.MANAGER.value)


def _replace_scenarios(db: DbSession, tool: Tool, codes: List[str]) -> None:
    wanted = {code for code in (codes or []) if code}
    scenarios = {
        row.code: row
        for row in db.scalars(select(KnowledgeScenario).where(KnowledgeScenario.code.in_(wanted)))
    }
    unknown = sorted(wanted - set(scenarios))
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知场景：{', '.join(unknown)}")
    for row in list(tool.scenario_rows):
        db.delete(row)
    db.flush()
    for code in wanted:
        db.add(ToolScenarioLink(tool_id=tool.id, scenario_id=scenarios[code].id))


def _usage_out(row: ToolUsage) -> ToolUsageOut:
    return ToolUsageOut(
        id=row.id,
        tool_code=row.tool_code,
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


def _usage_events(db: DbSession, code: str, limit: int = 20) -> List[ToolUsageOut]:
    rows = db.scalars(
        select(ToolUsage)
        .options(selectinload(ToolUsage.used_by))
        .where(ToolUsage.tool_code == code)
        .order_by(ToolUsage.used_at.desc(), ToolUsage.id.desc())
        .limit(limit)
    ).all()
    return [_usage_out(row) for row in rows]


def _require_tool(db: DbSession, code: str, user, *, allow_hidden: bool = False) -> Tool:
    tool = db.scalar(_tool_query().where(Tool.code == code))
    if tool is None:
        raise HTTPException(status_code=404, detail=f"工具 {code} 不存在")
    if not tool.is_active or tool.status not in VISIBLE_TOOL_STATUSES:
        is_owner = tool.owner_user_id is not None and tool.owner_user_id == user.id
        if not (allow_hidden and (_is_manager(user) or is_owner)):
            raise HTTPException(status_code=404, detail=f"工具 {code} 不存在")
    return tool


def _tool_query():
    return select(Tool).options(
        selectinload(Tool.scenario_rows).selectinload(ToolScenarioLink.scenario),
        selectinload(Tool.owner_user),
    )


def _visible_knowledge(db: DbSession, code: str, limit: int = 6):
    rows = db.scalars(
        select(KnowledgeItem)
        .options(
            selectinload(KnowledgeItem.tag_rows),
            selectinload(KnowledgeItem.scenario_rows).selectinload(KnowledgeScenarioLink.scenario),
            selectinload(KnowledgeItem.workflow_links),
            selectinload(KnowledgeItem.verified_by),
        )
        .where(
            KnowledgeItem.tool_code == code,
            KnowledgeItem.status.in_(VISIBLE_KNOWLEDGE),
            KnowledgeItem.type != "STANDARD",
        )
        .order_by(KnowledgeItem.is_best_practice.desc(), KnowledgeItem.updated_at.desc())
        .limit(limit)
    ).all()
    stats = knowledge_match.effectiveness_stats(db, [row.id for row in rows])
    return [knowledge_match.to_brief(row, stats.get(row.id, (0, 0, None))) for row in rows]


def _workflow_steps(db: DbSession, code: str) -> List[ToolWorkflowStepOut]:
    """反查哪些标准步骤契约引用了这个工具。"""
    templates = {row.step_no: row for row in db.scalars(select(WorkflowTemplate)).all()}
    result: List[ToolWorkflowStepOut] = []
    for contract in db.scalars(select(StepContract)).all():
        if code not in (contract.tool_codes or []):
            continue
        step = templates.get(contract.step_no)
        if step is None:
            continue
        result.append(
            ToolWorkflowStepOut(step_no=step.step_no, name=step.name, stage_no=step.stage_no)
        )
    return sorted(result, key=lambda row: (row.stage_no, row.step_no))


@router.get("/meta", response_model=ToolMetaOut, summary="工具分类、难度与场景字典")
def tool_meta(db: DbSession):
    return ToolMetaOut(
        category_labels=CATEGORY_LABELS,
        level_labels=TOOL_LEVEL_LABELS,
        difficulty_labels=DIFFICULTY_LABELS,
        scenarios=knowledge_match.scenario_list(db),
    )


@router.get(
    "/grouped",
    response_model=List[ToolCategoryGroup],
    summary="工具箱（按诊断/设计/落地/监控分组）",
)
def grouped(
    db: DbSession,
    user: CurrentUser,
    status_: Optional[ToolStatus] = Query(default=None, alias="status"),
):
    stmt = _tool_query().where(Tool.is_active.is_(True))
    if status_ is None:
        stmt = stmt.where(Tool.status.in_(VISIBLE_TOOL_STATUSES))
    else:
        if status_.value not in VISIBLE_TOOL_STATUSES and not _is_manager(user):
            raise HTTPException(status_code=403, detail="只有流程管理科可以查看未发布工具")
        stmt = stmt.where(Tool.status == status_.value)
    rows = db.scalars(stmt.order_by(Tool.category, Tool.sort_order)).all()
    counts = knowledge_match.knowledge_counts_by_tool(db, [row.code for row in rows])
    buckets: dict = {}
    for row in rows:
        tool = ToolOut.model_validate(row).model_copy(
            update={"knowledge_count": counts.get(row.code, 0)}
        )
        buckets.setdefault(row.category, []).append(tool)
    order = [
        ToolCategory.DIAGNOSE.value,
        ToolCategory.DESIGN.value,
        ToolCategory.DEPLOY.value,
        ToolCategory.MONITOR.value,
    ]
    return [
        ToolCategoryGroup(
            category=cat,
            label=CATEGORY_LABELS.get(cat, cat),
            count=len(buckets.get(cat, [])),
            tools=buckets.get(cat, []),
        )
        for cat in order
        if buckets.get(cat)
    ]


@router.post("/match", response_model=ToolMatchResponse, summary="按问题/场景匹配工具")
def match_tools(payload: ToolMatchRequest, db: DbSession):
    hits = tool_match.match_tools(
        db,
        problem=payload.problem,
        scenario_codes=payload.scenario_codes,
        category_filters=payload.category_filters,
        stage_no=payload.stage_no,
        step_no=payload.step_no,
        sort=payload.sort,
        limit=payload.limit,
    )
    return ToolMatchResponse(
        problem=payload.problem,
        scenario_codes=payload.scenario_codes,
        hits=hits,
        hint=tool_match.HINT,
    )


@router.get("", response_model=List[ToolBrief], summary="工具清单（可筛选）")
def list_tools(
    db: DbSession,
    user: CurrentUser,
    category: Optional[ToolCategory] = None,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
    keyword: Optional[str] = None,
    status_: Optional[ToolStatus] = Query(default=None, alias="status"),
):
    stmt = _tool_query().where(Tool.is_active.is_(True))
    if status_ is None:
        stmt = stmt.where(Tool.status.in_(VISIBLE_TOOL_STATUSES))
    else:
        if status_.value not in VISIBLE_TOOL_STATUSES and not _is_manager(user):
            raise HTTPException(status_code=403, detail="只有流程管理科可以查看未发布工具")
        stmt = stmt.where(Tool.status == status_.value)
    if category is not None:
        stmt = stmt.where(Tool.category == category.value)
    if stage_no is not None:
        stmt = stmt.where(Tool.stage_no == stage_no)
    if keyword:
        like = f"%{keyword}%"
        stmt = stmt.where(
            or_(
                Tool.name.like(like),
                Tool.alias.like(like),
                Tool.purpose.like(like),
                Tool.code.like(like),
            )
        )
    rows = db.scalars(stmt.order_by(Tool.category, Tool.sort_order)).all()
    counts = knowledge_match.knowledge_counts_by_tool(db, [row.code for row in rows])
    return [
        ToolBrief.model_validate(row).model_copy(
            update={"knowledge_count": counts.get(row.code, 0)}
        )
        for row in rows
    ]


@router.get(
    "/{code}", response_model=ToolDetailOut, summary="工具详情（含步骤、关联知识与步骤引用）"
)
def get_tool(code: str, db: DbSession, user: CurrentUser):
    tool = _require_tool(db, code, user, allow_hidden=True)
    base = ToolOut.model_validate(tool).model_dump()
    used, effective, rate = tool_match.tool_usage(db, [code]).get(code, (0, 0, None))
    knowledge_count = knowledge_match.knowledge_counts_by_tool(db, [code]).get(code, 0)
    base["knowledge_count"] = knowledge_count
    return ToolDetailOut(
        **base,
        usage=ToolUsageSummary(used=used, effective=effective, rate=rate),
        knowledge=_visible_knowledge(db, code),
        workflow_steps=_workflow_steps(db, code),
        usage_events=_usage_events(db, code),
    )


@router.post(
    "",
    response_model=ToolDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建工具草稿（流程管理科/流程 Owner）",
)
def create_tool(payload: ToolCreate, db: DbSession, user: WriteUser):
    code = payload.code.upper()
    if db.scalar(select(Tool).where(Tool.code == code)):
        raise HTTPException(status_code=409, detail=f"工具编码 {code} 已存在")
    data = as_columns(payload.model_dump(exclude={"scenario_codes"}))
    data.update(
        code=code,
        status=ToolStatus.DRAFT.value,
        version=1,
        owner_user_id=payload.owner_user_id or user.id,
    )
    tool = Tool(**data)
    db.add(tool)
    db.flush()
    _replace_scenarios(db, tool, payload.scenario_codes)
    audit_service.record(db, user, "CREATE", "tool", tool.id, f"新增工具草稿《{tool.name}》")
    db.commit()
    tool = _require_tool(db, code, user, allow_hidden=True)
    return get_tool(code, db, user)


@router.patch("/{code}", response_model=ToolDetailOut, summary="更新工具（草稿/待审核）")
def update_tool(code: str, payload: ToolUpdate, db: DbSession, user: WriteUser):
    tool = _require_tool(db, code, user, allow_hidden=True)
    ensure_can_edit_owned(user, tool.owner_user_id, tool.owner)
    if not _is_manager(user) and tool.status not in (
        ToolStatus.DRAFT.value,
        ToolStatus.IN_REVIEW.value,
    ):
        raise HTTPException(status_code=403, detail="已发布的工具需要流程管理科修改")

    data = as_columns(payload.model_dump(exclude_unset=True, exclude={"scenario_codes"}))
    for field, value in data.items():
        setattr(tool, field, value)
    if "scenario_codes" in payload.model_fields_set:
        _replace_scenarios(db, tool, payload.scenario_codes or [])

    tool.version = (tool.version or 1) + 1
    if tool.status == ToolStatus.VERIFIED.value:
        # 内容变了，旧验证结论不再成立
        tool.status = ToolStatus.PUBLISHED.value
        tool.last_verified_at = None
        tool.review_due_at = None
        tool.reviewed_by_user_id = None
        tool.reviewed_at = None
    audit_service.record(
        db, user, "UPDATE", "tool", tool.id, f"更新工具《{tool.name}》到 v{tool.version}"
    )
    db.commit()
    return get_tool(code, db, user)


@router.post("/{code}/submit", response_model=ToolDetailOut, summary="提交工具审核")
def submit_tool(code: str, db: DbSession, user: WriteUser):
    tool = _require_tool(db, code, user, allow_hidden=True)
    ensure_can_edit_owned(user, tool.owner_user_id, tool.owner)
    if tool.status != ToolStatus.DRAFT.value:
        raise HTTPException(status_code=409, detail="只有草稿可以提交审核")
    tool.status = ToolStatus.IN_REVIEW.value
    tool.submitted_at = utcnow()
    audit_service.record(db, user, "UPDATE", "tool", tool.id, f"提交工具《{tool.name}》审核")
    db.commit()
    return get_tool(code, db, user)


@router.post("/{code}/review", response_model=ToolDetailOut, summary="审核工具（Manager）")
def review_tool(code: str, payload: ToolReviewRequest, db: DbSession, user: ManagerUser):
    tool = _require_tool(db, code, user, allow_hidden=True)
    if tool.status != ToolStatus.IN_REVIEW.value:
        raise HTTPException(status_code=409, detail="只有待审核的工具可以审核")
    if payload.decision == "APPROVE":
        tool.status = ToolStatus.VERIFIED.value
        tool.last_verified_at = utcnow()
        tool.review_due_at = date.today() + timedelta(days=365)
        action = "通过"
    else:
        tool.status = ToolStatus.DRAFT.value
        action = "驳回"
    tool.reviewed_by_user_id = user.id
    tool.reviewed_at = utcnow()
    audit_service.record(
        db,
        user,
        "UPDATE",
        "tool",
        tool.id,
        f"{action}工具《{tool.name}》审核" + (f"：{payload.note}" if payload.note else ""),
    )
    db.commit()
    return get_tool(code, db, user)


@router.post("/{code}/archive", response_model=ToolDetailOut, summary="归档工具（Manager）")
def archive_tool(code: str, db: DbSession, user: ManagerUser):
    tool = _require_tool(db, code, user, allow_hidden=True)
    if tool.status == ToolStatus.ARCHIVED.value:
        raise HTTPException(status_code=409, detail="该工具已归档")
    tool.status = ToolStatus.ARCHIVED.value
    tool.is_active = False
    audit_service.record(db, user, "UPDATE", "tool", tool.id, f"归档工具《{tool.name}》")
    db.commit()
    return get_tool(code, db, user)


@router.post(
    "/{code}/usage",
    response_model=ToolUsageOut,
    status_code=status.HTTP_201_CREATED,
    summary="记录一次工具使用证据",
)
def record_tool_usage(code: str, payload: ToolUsageCreate, db: DbSession, user: WriteUser):
    _require_tool(db, code, user)

    step_no = (payload.step_no or "").strip() or None
    recent = utcnow() - timedelta(minutes=10)
    conditions = [
        ToolUsage.tool_code == code,
        ToolUsage.used_by_user_id == user.id,
        ToolUsage.outcome == payload.outcome,
        ToolUsage.used_at >= recent,
    ]
    if payload.project_id is None:
        conditions.append(ToolUsage.project_id.is_(None))
    else:
        conditions.append(ToolUsage.project_id == payload.project_id)
    if step_no is None:
        conditions.append(ToolUsage.step_no.is_(None))
    else:
        conditions.append(ToolUsage.step_no == step_no)
    duplicate = db.scalar(
        select(ToolUsage)
        .options(selectinload(ToolUsage.used_by))
        .where(*conditions)
        .order_by(ToolUsage.used_at.desc())
        .limit(1)
    )
    if duplicate is not None:
        return _usage_out(duplicate)

    row = ToolUsage(
        tool_code=code,
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
        "tool_usage",
        row.id,
        f"记录工具 {code} 使用证据：{knowledge_match.OUTCOME_LABELS.get(payload.outcome)}",
    )
    db.commit()
    row = db.scalar(
        select(ToolUsage).options(selectinload(ToolUsage.used_by)).where(ToolUsage.id == row.id)
    )
    return _usage_out(row)


@router.get(
    "/{code}/usage",
    response_model=List[ToolUsageOut],
    summary="工具的使用证据",
)
def list_tool_usage(
    code: str,
    db: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
):
    _require_tool(db, code, user, allow_hidden=True)
    return _usage_events(db, code, limit=limit)
