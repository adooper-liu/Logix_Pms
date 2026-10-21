"""五阶段标准工作流（全公司共用的操作手册）。"""

from __future__ import annotations

from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import DbSession
from app.models.project import WorkflowTemplate
from app.schemas.project import WorkflowStageOut, WorkflowStepOut

router = APIRouter(prefix="/workflow", tags=["标准工作流"])


@router.get("/stages", response_model=List[WorkflowStageOut], summary="五阶段 × 全部步骤")
def get_stages(db: DbSession):
    rows = db.scalars(
        select(WorkflowTemplate).order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)
    ).all()
    grouped: Dict[int, WorkflowStageOut] = {}
    for row in rows:
        stage = grouped.get(row.stage_no)
        if stage is None:
            stage = WorkflowStageOut(
                stage_no=row.stage_no,
                stage_name=row.stage_name,
                stage_goal=row.stage_goal,
                steps=[],
            )
            grouped[row.stage_no] = stage
        stage.steps.append(WorkflowStepOut.model_validate(row))
    return [grouped[k] for k in sorted(grouped)]


@router.get("/steps", response_model=List[WorkflowStepOut], summary="全部步骤（扁平）")
def get_steps(db: DbSession, stage_no: Optional[int] = None):
    stmt = select(WorkflowTemplate)
    if stage_no is not None:
        stmt = stmt.where(WorkflowTemplate.stage_no == stage_no)
    rows = db.scalars(stmt.order_by(WorkflowTemplate.stage_no, WorkflowTemplate.sort_order)).all()
    return [WorkflowStepOut.model_validate(r) for r in rows]


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
        steps=[WorkflowStepOut.model_validate(r) for r in rows],
    )
