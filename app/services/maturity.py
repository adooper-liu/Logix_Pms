"""成熟度评估、阶段门禁与跨层覆盖度。"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import utcnow
from app.models.enums import GateConclusion, MaturityDimension
from app.models.maturity import GateAttestation, MaturityAssessment
from app.models.monitor import KpiDefinition
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument
from app.models.project import Project
from app.models.user import User
from app.schemas.maturity import (
    CoverageRowOut,
    CoverageSummaryOut,
    GateAttestationOut,
    MaturityAssessmentOut,
)

DIMENSION_LABELS: Dict[str, str] = {
    MaturityDimension.GOVERNANCE.value: "治理与责任",
    MaturityDimension.PROCESS.value: "流程资产",
    MaturityDimension.DATA.value: "数据与指标",
    MaturityDimension.EXECUTION.value: "执行与系统",
    MaturityDimension.MEASUREMENT.value: "度量与改善",
}

CONCLUSION_LABELS: Dict[str, str] = {
    GateConclusion.PASS.value: "通过",
    GateConclusion.PATCH.value: "修补后通过",
    GateConclusion.NARROW.value: "缩小范围",
    GateConclusion.STOP.value: "停止",
}


class MaturityError(ValueError):
    """成熟度/门禁业务规则拒绝。"""


def _pct(part: int, total: int) -> float:
    return round(part / total * 100, 1) if total else 100.0


def assessment_out(db: Session, row: MaturityAssessment) -> MaturityAssessmentOut:
    process = db.get(ProcessArch, row.process_id)
    return MaturityAssessmentOut(
        id=row.id,
        process_id=row.process_id,
        process_code=process.code if process else None,
        process_name=process.name if process else None,
        org_unit_id=row.org_unit_id,
        dimension=row.dimension,
        dimension_label=DIMENSION_LABELS.get(row.dimension, row.dimension),
        level=row.level,
        evidence_url=row.evidence_url,
        assessed_by_user_id=row.assessed_by_user_id,
        assessed_by=row.assessed_by.display_name if row.assessed_by else None,
        assessed_at=row.assessed_at,
        valid_until=row.valid_until,
        note=row.note,
    )


def create_assessment(db: Session, data: dict, user: User) -> MaturityAssessment:
    if db.get(ProcessArch, data["process_id"]) is None:
        raise MaturityError("流程不存在")
    if not (data.get("evidence_url") or "").strip():
        raise MaturityError("成熟度评分必须附证据链接")
    row = MaturityAssessment(
        process_id=data["process_id"],
        org_unit_id=data.get("org_unit_id"),
        dimension=data["dimension"],
        level=data["level"],
        evidence_url=data["evidence_url"],
        assessed_by_user_id=user.id,
        assessed_at=utcnow(),
        valid_until=data.get("valid_until"),
        note=data.get("note"),
    )
    db.add(row)
    db.flush()
    return row


def list_assessments(
    db: Session,
    process_id: Optional[int] = None,
    org_unit_id: Optional[int] = None,
    dimension: Optional[str] = None,
    limit: int = 200,
) -> List[MaturityAssessment]:
    stmt = (
        select(MaturityAssessment)
        .options(joinedload(MaturityAssessment.assessed_by))
        .order_by(MaturityAssessment.assessed_at.desc(), MaturityAssessment.id.desc())
    )
    if process_id is not None:
        stmt = stmt.where(MaturityAssessment.process_id == process_id)
    if org_unit_id is not None:
        stmt = stmt.where(MaturityAssessment.org_unit_id == org_unit_id)
    if dimension:
        stmt = stmt.where(MaturityAssessment.dimension == dimension)
    return list(db.scalars(stmt.limit(limit)).all())


def gate_out(db: Session, row: GateAttestation) -> GateAttestationOut:
    project = db.get(Project, row.project_id)
    return GateAttestationOut(
        id=row.id,
        project_id=row.project_id,
        project_code=project.code if project else None,
        stage_no=row.stage_no,
        gate_code=row.gate_code,
        exit_criteria=row.exit_criteria,
        evidence_url=row.evidence_url,
        conclusion=row.conclusion,
        conclusion_label=CONCLUSION_LABELS.get(row.conclusion, row.conclusion),
        signed_by_user_id=row.signed_by_user_id,
        signed_by=row.signed_by.display_name if row.signed_by else None,
        signed_at=row.signed_at,
        note=row.note,
    )


def create_gate(db: Session, data: dict, user: User) -> GateAttestation:
    project = db.get(Project, data["project_id"])
    if project is None:
        raise MaturityError("项目不存在")
    if data["stage_no"] != project.current_stage:
        raise MaturityError("只能签收项目当前阶段的门禁")
    if not (data.get("evidence_url") or "").strip():
        raise MaturityError("门禁签收必须附证据链接")
    row = GateAttestation(
        project_id=project.id,
        stage_no=data["stage_no"],
        gate_code=data.get("gate_code") or "STAGE_GATE",
        exit_criteria=data.get("exit_criteria"),
        evidence_url=data["evidence_url"],
        conclusion=data["conclusion"],
        signed_by_user_id=user.id,
        signed_at=utcnow(),
        note=data.get("note"),
    )
    db.add(row)
    db.flush()
    return row


def latest_gate(db: Session, project_id: int, stage_no: int) -> Optional[GateAttestation]:
    return db.scalar(
        select(GateAttestation)
        .options(joinedload(GateAttestation.signed_by))
        .where(
            GateAttestation.project_id == project_id,
            GateAttestation.stage_no == stage_no,
        )
        .order_by(GateAttestation.signed_at.desc(), GateAttestation.id.desc())
        .limit(1)
    )


def list_gates(db: Session, project_id: int, limit: int = 100) -> List[GateAttestation]:
    return list(
        db.scalars(
            select(GateAttestation)
            .options(joinedload(GateAttestation.signed_by))
            .where(GateAttestation.project_id == project_id)
            .order_by(GateAttestation.stage_no, GateAttestation.signed_at.desc())
            .limit(limit)
        ).all()
    )


def ensure_advance_allowed(db: Session, project: Project, target_stage: int) -> None:
    """启用门禁时，进入下一阶段前每个经过的阶段都必须有 PASS 签收。"""
    if not project.gate_required or target_stage <= project.current_stage:
        return
    missing: List[str] = []
    for stage_no in range(project.current_stage, target_stage):
        gate = latest_gate(db, project.id, stage_no)
        if gate is None:
            missing.append(f"阶段{stage_no}未签收")
        elif gate.conclusion != GateConclusion.PASS.value:
            missing.append(
                f"阶段{stage_no}结论为{CONCLUSION_LABELS.get(gate.conclusion, gate.conclusion)}"
            )
    if missing:
        raise MaturityError("门禁未通过，不能进入下一阶段：" + "；".join(missing))


def coverage_summary(db: Session) -> CoverageSummaryOut:
    nodes = list(
        db.scalars(
            select(ProcessArch).where(ProcessArch.level == 4, ProcessArch.is_draft.is_(False))
        ).all()
    )
    parent_ids = {node.parent_id for node in nodes if node.parent_id}
    parents = {
        row.id: row
        for row in db.scalars(
            select(ProcessArch).where(ProcessArch.id.in_(parent_ids or {-1}))
        ).all()
    }
    doc_parents = set(
        db.scalars(
            select(ProcessDocument.process_id).where(
                ProcessDocument.is_active.is_(True),
                ProcessDocument.process_id.in_(parent_ids or {-1}),
            )
        ).all()
    )
    kpi_activities = set(
        db.scalars(
            select(KpiDefinition.activity_id).where(
                KpiDefinition.is_active.is_(True),
                KpiDefinition.activity_id.is_not(None),
            )
        ).all()
    )

    buckets: Dict[int, Dict[str, int]] = {}
    for node in nodes:
        bucket = buckets.setdefault(
            node.parent_id or 0,
            {"total": 0, "owner": 0, "document": 0, "kpi": 0},
        )
        bucket["total"] += 1
        if node.owner_user_id is not None or (node.owner or "").strip():
            bucket["owner"] += 1
        if node.parent_id in doc_parents:
            bucket["document"] += 1
        if node.id in kpi_activities:
            bucket["kpi"] += 1

    rows: List[CoverageRowOut] = []
    for parent_id, bucket in sorted(buckets.items()):
        parent = parents.get(parent_id)
        rows.append(
            CoverageRowOut(
                process_id=parent_id,
                process_code=parent.code if parent else "—",
                process_name=parent.name if parent else "未归属 L3",
                l4_total=bucket["total"],
                l4_with_owner=bucket["owner"],
                l4_with_document=bucket["document"],
                l4_with_kpi=bucket["kpi"],
                owner_coverage_pct=_pct(bucket["owner"], bucket["total"]),
                document_coverage_pct=_pct(bucket["document"], bucket["total"]),
                kpi_coverage_pct=_pct(bucket["kpi"], bucket["total"]),
            )
        )

    total = sum(bucket["total"] for bucket in buckets.values())
    return CoverageSummaryOut(
        rows=rows,
        l4_total=total,
        l4_with_owner=sum(bucket["owner"] for bucket in buckets.values()),
        l4_with_document=sum(bucket["document"] for bucket in buckets.values()),
        l4_with_kpi=sum(bucket["kpi"] for bucket in buckets.values()),
    )


def coverage_gaps(db: Session) -> List[dict]:
    """治理扫描用：逐 L4 返回缺失项，便于生成待办。"""
    nodes = list(
        db.scalars(
            select(ProcessArch).where(ProcessArch.level == 4, ProcessArch.is_draft.is_(False))
        ).all()
    )
    parent_ids = {node.parent_id for node in nodes if node.parent_id}
    doc_parents = set(
        db.scalars(
            select(ProcessDocument.process_id).where(
                ProcessDocument.is_active.is_(True),
                ProcessDocument.process_id.in_(parent_ids or {-1}),
            )
        ).all()
    )
    kpi_activities = set(
        db.scalars(
            select(KpiDefinition.activity_id).where(
                KpiDefinition.is_active.is_(True),
                KpiDefinition.activity_id.is_not(None),
            )
        ).all()
    )
    gaps: List[dict] = []
    for node in nodes:
        missing = []
        if node.owner_user_id is None and not (node.owner or "").strip():
            missing.append("owner")
        if node.parent_id not in doc_parents:
            missing.append("document")
        if node.id not in kpi_activities:
            missing.append("kpi")
        if missing:
            gaps.append({"node": node, "missing": missing})
    return gaps


def avg_level_by_dimension(db: Session, process_id: int) -> Dict[str, float]:
    rows = list(
        db.scalars(
            select(MaturityAssessment).where(MaturityAssessment.process_id == process_id)
        ).all()
    )
    latest: Dict[str, MaturityAssessment] = {}
    for row in rows:
        current = latest.get(row.dimension)
        if current is None or row.assessed_at > current.assessed_at:
            latest[row.dimension] = row
    return {dim: row.level for dim, row in latest.items()}


def is_valid(row: MaturityAssessment, today: Optional[date] = None) -> bool:
    today = today or date.today()
    return row.valid_until is None or row.valid_until >= today


__all__: Sequence[str] = [
    "CONCLUSION_LABELS",
    "DIMENSION_LABELS",
    "MaturityError",
    "assessment_out",
    "coverage_gaps",
    "coverage_summary",
    "create_assessment",
    "create_gate",
    "ensure_advance_allowed",
    "gate_out",
    "latest_gate",
    "list_assessments",
    "list_gates",
]
