"""成熟度评估、阶段门禁与跨层覆盖度 API。"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentUser, DbSession, ManagerUser, WriteUser, require_manager
from app.models.enums import MaturityDimension
from app.schemas.maturity import (
    CoverageSummaryOut,
    GateAttestationCreate,
    GateAttestationOut,
    MaturityAssessmentCreate,
    MaturityAssessmentOut,
    MaturityMetaOut,
)
from app.services import audit as audit_service
from app.services import maturity as maturity_service

router = APIRouter(prefix="/maturity", tags=["成熟度与门禁"])


def _raise(exc: maturity_service.MaturityError) -> None:
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/meta", response_model=MaturityMetaOut, summary="成熟度维度与门禁结论标签")
def meta():
    return MaturityMetaOut(
        dimension_labels=maturity_service.DIMENSION_LABELS,
        conclusion_labels=maturity_service.CONCLUSION_LABELS,
    )


@router.get(
    "/assessments",
    response_model=List[MaturityAssessmentOut],
    summary="成熟度评估记录",
)
def list_assessments(
    db: DbSession,
    process_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
    dimension: Optional[MaturityDimension] = None,
    limit: int = Query(default=200, ge=1, le=500),
):
    rows = maturity_service.list_assessments(
        db,
        process_id=process_id,
        org_unit_id=org_unit_id,
        dimension=dimension.value if dimension else None,
        limit=limit,
    )
    return [maturity_service.assessment_out(db, row) for row in rows]


@router.post(
    "/assessments",
    response_model=MaturityAssessmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="新增成熟度评估（Manager）",
)
def create_assessment(payload: MaturityAssessmentCreate, db: DbSession, user: ManagerUser):
    try:
        row = maturity_service.create_assessment(db, payload.model_dump(), user)
    except maturity_service.MaturityError as exc:
        _raise(exc)
    audit_service.record(
        db,
        user,
        "CREATE",
        "maturity_assessment",
        row.id,
        f"新增成熟度评估：流程 {row.process_id} / {row.dimension} / L{row.level}",
    )
    db.commit()
    db.refresh(row)
    return maturity_service.assessment_out(db, row)


@router.get(
    "/gates",
    response_model=List[GateAttestationOut],
    summary="项目的阶段门禁记录",
)
def list_gates(
    db: DbSession,
    user: CurrentUser,
    project_id: int = Query(ge=1),
    limit: int = Query(default=100, ge=1, le=200),
):
    from app.models.project import Project
    from app.services import org_access

    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "项目不存在")
    org_access.ensure_visible(db, user, project.org_unit_id)
    return [
        maturity_service.gate_out(db, row)
        for row in maturity_service.list_gates(db, project_id, limit=limit)
    ]


@router.post(
    "/gates",
    response_model=GateAttestationOut,
    status_code=status.HTTP_201_CREATED,
    summary="签收阶段门禁（Manager）",
)
def create_gate(payload: GateAttestationCreate, db: DbSession, user: WriteUser):
    if payload.purpose == "STAGE_GATE":
        require_manager(user)
    try:
        row = maturity_service.create_gate(db, payload.model_dump(), user)
    except maturity_service.MaturityError as exc:
        _raise(exc)
    audit_service.record(
        db,
        user,
        "CREATE",
        "gate_attestation",
        row.id,
        f"签收项目 {row.project_id} 阶段{row.stage_no}门禁：{row.conclusion}",
    )
    db.commit()
    db.refresh(row)
    return maturity_service.gate_out(db, row)


@router.get(
    "/coverage",
    response_model=CoverageSummaryOut,
    summary="L4 活动 Owner/制度/KPI 覆盖率（Manager）",
)
def coverage(db: DbSession, user: ManagerUser):
    return maturity_service.coverage_summary(db)
