"""方法论工具箱：问题驱动匹配、工具清单与详情。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.deliverable import StepContract
from app.models.enums import KnowledgeStatus, ToolCategory, ToolLevel
from app.models.knowledge import KnowledgeItem, KnowledgeScenarioLink
from app.models.project import WorkflowTemplate
from app.models.tool import Tool, ToolScenarioLink
from app.schemas.tool import (
    ToolBrief,
    ToolCategoryGroup,
    ToolDetailOut,
    ToolMatchRequest,
    ToolMatchResponse,
    ToolMetaOut,
    ToolOut,
    ToolUsageSummary,
    ToolWorkflowStepOut,
)
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
def grouped(db: DbSession):
    rows = db.scalars(
        _tool_query().where(Tool.is_active.is_(True)).order_by(Tool.category, Tool.sort_order)
    ).all()
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
    category: Optional[ToolCategory] = None,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
    keyword: Optional[str] = None,
):
    stmt = _tool_query().where(Tool.is_active.is_(True))
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
def get_tool(code: str, db: DbSession):
    tool = db.scalar(_tool_query().where(Tool.code == code))
    if tool is None:
        raise HTTPException(status_code=404, detail=f"工具 {code} 不存在")
    base = ToolOut.model_validate(tool).model_dump()
    used, effective, rate = tool_match.tool_usage(db, [code]).get(code, (0, 0, None))
    knowledge_count = knowledge_match.knowledge_counts_by_tool(db, [code]).get(code, 0)
    base["knowledge_count"] = knowledge_count
    return ToolDetailOut(
        **base,
        usage=ToolUsageSummary(used=used, effective=effective, rate=rate),
        knowledge=_visible_knowledge(db, code),
        workflow_steps=_workflow_steps(db, code),
    )
