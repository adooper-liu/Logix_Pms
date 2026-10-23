"""方法论工具箱：清单、分组、按问题找工具。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import or_, select

from app.api.deps import DbSession
from app.models.enums import ToolCategory, ToolLevel
from app.models.tool import Tool
from app.schemas.tool import (
    ToolBrief,
    ToolCategoryGroup,
    ToolMatchHit,
    ToolMatchRequest,
    ToolMatchResponse,
    ToolOut,
)
from app.services import tool_finder

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


@router.get("/meta", summary="工具分类与使用要求标签")
def tool_meta():
    return {
        "category_labels": CATEGORY_LABELS,
        "level_labels": TOOL_LEVEL_LABELS,
    }


@router.get(
    "/grouped",
    response_model=List[ToolCategoryGroup],
    summary="工具箱（按诊断/设计/落地/监控分组）",
)
def grouped(db: DbSession):
    rows = db.scalars(select(Tool).order_by(Tool.category, Tool.sort_order)).all()
    buckets: dict = {}
    for row in rows:
        buckets.setdefault(row.category, []).append(ToolOut.model_validate(row))
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


@router.post("/match", response_model=ToolMatchResponse, summary="按问题找工具")
def match_tools(payload: ToolMatchRequest, db: DbSession):
    tools = db.scalars(select(Tool)).all()
    hits = tool_finder.match(tools, payload.problem, payload.stage_no)
    return ToolMatchResponse(
        problem=payload.problem,
        hits=[
            ToolMatchHit(tool=ToolOut.model_validate(t), score=s, matched_on=m) for t, s, m in hits
        ],
        hint=tool_finder.HINT,
    )


@router.get("", response_model=List[ToolBrief], summary="工具清单（可筛选）")
def list_tools(
    db: DbSession,
    category: Optional[ToolCategory] = None,
    stage_no: Optional[int] = Query(default=None, ge=1, le=5),
    keyword: Optional[str] = None,
):
    stmt = select(Tool)
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
    return [
        ToolBrief.model_validate(t)
        for t in db.scalars(stmt.order_by(Tool.category, Tool.sort_order)).all()
    ]


@router.get("/{code}", response_model=ToolOut, summary="工具详情（含 5 步标准操作）")
def get_tool(code: str, db: DbSession):
    tool = db.scalar(select(Tool).where(Tool.code == code))
    if tool is None:
        raise HTTPException(status_code=404, detail=f"工具 {code} 不存在")
    return ToolOut.model_validate(tool)
