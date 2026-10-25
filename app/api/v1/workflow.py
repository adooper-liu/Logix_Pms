"""五阶段标准工作流（全公司共用的操作手册）。"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.project import WorkflowTemplate
from app.schemas.project import WorkflowStageOut, WorkflowStepOut
from app.services import knowledge_match

router = APIRouter(prefix="/workflow", tags=["标准工作流"])


def _step_out(db: DbSession, rows: List[WorkflowTemplate]) -> List[WorkflowStepOut]:
    """步骤出参统一补上「推荐知识数」，列表与详情口径一致。"""
    counts = knowledge_match.step_counts(db, [(row.stage_no, row.step_no) for row in rows])
    return [
        WorkflowStepOut.model_validate(row).model_copy(
            update={"knowledge_count": counts.get((row.stage_no, row.step_no), 0)}
        )
        for row in rows
    ]


@router.get("/stages", response_model=List[WorkflowStageOut], summary="五阶段 × 全部步骤")
def get_stages(db: DbSession):
    rows = db.scalars(
        select(WorkflowTemplate).order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)
    ).all()
    steps = _step_out(db, rows)
    grouped: Dict[int, WorkflowStageOut] = {}
    for row, step in zip(rows, steps, strict=False):
        stage = grouped.get(row.stage_no)
        if stage is None:
            stage = WorkflowStageOut(
                stage_no=row.stage_no,
                stage_name=row.stage_name,
                stage_goal=row.stage_goal,
                steps=[],
            )
            grouped[row.stage_no] = stage
        stage.steps.append(step)
    counts = knowledge_match.stage_counts(db, grouped.keys())
    for stage_no, stage in grouped.items():
        stage.knowledge_count = counts.get(stage_no, 0)
    return [grouped[k] for k in sorted(grouped)]


@router.get("/steps", response_model=List[WorkflowStepOut], summary="全部步骤（扁平）")
def get_steps(db: DbSession, stage_no: Optional[int] = None):
    stmt = select(WorkflowTemplate)
    if stage_no is not None:
        stmt = stmt.where(WorkflowTemplate.stage_no == stage_no)
    rows = db.scalars(stmt.order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)).all()
    return _step_out(db, rows)


@router.get("/stages/{stage_no}", response_model=WorkflowStageOut, summary="单个阶段的步骤")
def get_stage(stage_no: int, db: DbSession):
    rows = db.scalars(
        select(WorkflowTemplate)
        .where(WorkflowTemplate.stage_no == stage_no)
        .order_by(WorkflowTemplate.sort_order)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail=f"阶段 {stage_no} 不存在")
    return WorkflowStageOut(
        stage_no=stage_no,
        stage_name=rows[0].stage_name,
        stage_goal=rows[0].stage_goal,
        knowledge_count=knowledge_match.stage_counts(db, [stage_no]).get(stage_no, 0),
        steps=_step_out(db, rows),
    )
