"""决策表 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession, ManagerUser
from app.models.decision import DecisionTable
from app.schemas.decision import (
    DecisionEvaluateIn,
    DecisionEvaluateOut,
    DecisionTableCreate,
    DecisionTableOut,
    DecisionTableUpdate,
)
from app.services import audit as audit_service
from app.services import decision as decision_service

router = APIRouter(prefix="/decisions", tags=["决策表"])


def _fail(exc: decision_service.DecisionError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=List[DecisionTableOut], summary="决策表清单")
def list_decisions(
    db: DbSession,
    user: CurrentUser,
    process_id: Optional[int] = None,
    node_key: Optional[str] = None,
    include_inactive: bool = False,
):
    return [
        decision_service.table_out(row)
        for row in decision_service.list_tables(
            db,
            process_id=process_id,
            node_key=node_key,
            include_inactive=include_inactive,
        )
    ]


@router.get("/{code}", response_model=DecisionTableOut, summary="决策表详情")
def get_decision(code: str, db: DbSession, user: CurrentUser):
    try:
        return decision_service.table_out(decision_service.require_table(db, code))
    except decision_service.DecisionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=DecisionTableOut,
    status_code=status.HTTP_201_CREATED,
    summary="新建决策表（Manager）",
)
def create_decision(payload: DecisionTableCreate, db: DbSession, user: ManagerUser):
    if db.scalar(select(DecisionTable).where(DecisionTable.code == payload.code)):
        raise HTTPException(status_code=409, detail=f"决策表编码 {payload.code} 已存在")
    row = DecisionTable(**payload.model_dump())
    db.add(row)
    db.flush()
    audit_service.record(
        db, user, "CREATE", "decision_table", row.id, f"新建决策表 {row.code} {row.name}"
    )
    db.commit()
    db.refresh(row)
    return decision_service.table_out(row)


@router.patch("/{table_id}", response_model=DecisionTableOut, summary="修改决策表（Manager）")
def update_decision(table_id: int, payload: DecisionTableUpdate, db: DbSession, user: ManagerUser):
    row = db.get(DecisionTable, table_id)
    if row is None:
        raise HTTPException(status_code=404, detail="决策表不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    row.version = (row.version or 1) + 1
    audit_service.record(
        db, user, "UPDATE", "decision_table", row.id, f"修改决策表 {row.code} 到 v{row.version}"
    )
    db.commit()
    db.refresh(row)
    return decision_service.table_out(row)


@router.post(
    "/{code}/evaluate",
    response_model=DecisionEvaluateOut,
    summary="按输入求值",
)
def evaluate_decision(code: str, payload: DecisionEvaluateIn, db: DbSession, user: CurrentUser):
    try:
        row = decision_service.require_table(db, code)
    except decision_service.DecisionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return decision_service.evaluate(row, payload.inputs)
