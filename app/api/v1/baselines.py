"""资产基线 API：创建快照、查看明细、与当前有效版本做差异审计。

基线不可变；创建后只用于对照，不随标准升级而改变。
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import DbSession, ManagerUser
from app.models.governance import GovernanceFinding
from app.schemas.baseline import (
    AuditScanResult,
    BaselineCreate,
    BaselineDetail,
    BaselineDiff,
    BaselineMeta,
    BaselineOut,
    FindingOut,
    FindingUpdate,
    GovernanceSummary,
)
from app.schemas.common import as_columns
from app.services import audit as audit_service
from app.services import baseline as baseline_service
from app.services import governance as governance_service

router = APIRouter(prefix="/baselines", tags=["资产基线"])


@router.get("/meta", response_model=BaselineMeta, summary="基线范围与差异状态标签")
def meta():
    return baseline_service.meta()


@router.get("", response_model=List[BaselineOut], summary="基线清单")
def list_baselines(db: DbSession, limit: int = Query(default=100, ge=1, le=500)):
    return [
        baseline_service.baseline_out(db, row) for row in baseline_service.list_baselines(db, limit)
    ]


@router.post(
    "",
    response_model=BaselineOut,
    status_code=status.HTTP_201_CREATED,
    summary="创建基线快照（MANAGER+）",
)
def create_baseline(payload: BaselineCreate, db: DbSession, user: ManagerUser):
    data = as_columns(payload.model_dump())
    try:
        baseline = baseline_service.create_baseline(db, data, user)
    except baseline_service.BaselineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db,
        user,
        "CREATE",
        "asset_baseline",
        baseline.id,
        f"创建基线 {baseline.code}（{baseline.name}，{baseline.item_count} 项）",
    )
    db.commit()
    db.refresh(baseline)
    return baseline_service.baseline_out(db, baseline)


@router.get(
    "/governance",
    response_model=GovernanceSummary,
    summary="治理概览：资产有效性、落后变体、固定旧版交付物、基线覆盖率",
)
def governance(db: DbSession):
    return baseline_service.governance_summary(db)


@router.get("/findings", response_model=List[FindingOut], summary="治理待办清单")
def list_findings(
    db: DbSession,
    status_: Optional[str] = Query(default=None, alias="status"),
    finding_type: Optional[str] = Query(default=None, alias="type"),
    limit: int = Query(default=200, ge=1, le=500),
):
    return [
        governance_service.finding_out(db, row)
        for row in governance_service.list_findings(db, status_, finding_type, limit)
    ]


@router.post(
    "/audit-scan",
    response_model=AuditScanResult,
    summary="执行一致性审计扫描（MANAGER+）：新增/刷新/自动关闭治理待办",
)
def audit_scan(db: DbSession, user: ManagerUser):
    result = governance_service.scan(db)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "governance_finding",
        None,
        f"一致性审计：扫描 {result.scanned} 项，新增 {result.created}，"
        f"自动关闭 {result.resolved}，通知 {result.notified}",
    )
    db.commit()
    return result


@router.patch(
    "/findings/{finding_id}",
    response_model=FindingOut,
    summary="忽略 / 重新打开治理待办（MANAGER+）",
)
def update_finding(finding_id: int, payload: FindingUpdate, db: DbSession, user: ManagerUser):
    finding = db.get(GovernanceFinding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="治理待办不存在")
    governance_service.set_status(db, finding, payload.status)
    audit_service.record(
        db,
        user,
        "UPDATE",
        "governance_finding",
        finding.id,
        f"治理待办 {finding.title} → {payload.status}",
    )
    db.commit()
    db.refresh(finding)
    return governance_service.finding_out(db, finding)


@router.get("/{baseline_id}", response_model=BaselineDetail, summary="基线明细（当时的标准版本）")
def get_baseline(baseline_id: int, db: DbSession):
    try:
        baseline = baseline_service.require_baseline(db, baseline_id)
    except baseline_service.BaselineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return baseline_service.baseline_detail(db, baseline)


@router.get("/{baseline_id}/diff", response_model=BaselineDiff, summary="基线 vs 当前有效版本")
def diff_baseline(baseline_id: int, db: DbSession):
    try:
        baseline = baseline_service.require_baseline(db, baseline_id)
        return baseline_service.diff_baseline(db, baseline)
    except baseline_service.BaselineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
