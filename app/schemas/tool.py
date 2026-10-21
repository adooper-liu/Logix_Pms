"""工具箱出入参。"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class ToolOut(ORMModel):
    id: int
    code: str
    name: str
    alias: Optional[str] = None
    category: str
    stage_no: int
    purpose: str
    when_to_use: str
    steps: List[str] = []
    template_ref: Optional[str] = None
    pitfalls: Optional[str] = None


class ToolBrief(ORMModel):
    id: int
    code: str
    name: str
    category: str
    stage_no: int
    purpose: str


class ToolCategoryGroup(BaseModel):
    category: str
    label: str
    count: int
    tools: List[ToolOut] = []


class ToolMatchRequest(BaseModel):
    problem: str = Field(min_length=2, description="用一句话描述遇到的问题，如：审批太多、周期太长")
    stage_no: Optional[int] = Field(default=None, ge=1, le=5)


class ToolMatchHit(BaseModel):
    tool: ToolOut
    score: float
    matched_on: List[str] = Field(description="命中的关键词")


class ToolMatchResponse(BaseModel):
    problem: str
    hits: List[ToolMatchHit]
    hint: str
