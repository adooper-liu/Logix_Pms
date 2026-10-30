"""项目证据登记、独立裁决与阶段门证据检查。"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.timeutil import utcnow
from app.models.evidence import ProjectEvidenceClaim
from app.schemas.evidence import ProjectEvidenceClaimOut

EVIDENCE_LEVEL_LABELS = {
    "L1": "现场观察数据",
    "L2": "系统日志数据",
    "L3": "业务结果数据",
    "L4": "外部对标数据",
    "L5": "反证数据",
}
EVIDENCE_TYPE_LABELS = {
    "OBSERVATION": "现场观测",
    "SYSTEM_LOG": "系统日志",
    "BUSINESS_RESULT": "业务结果",
    "INTERVIEW": "访谈记录",
    "DOCUMENT": "文件/记录",
    "INDUSTRY_BENCHMARK": "行业对标",
}
VERDICT_LABELS = {
    "PENDING": "待验证",
    "CONFIRMED": "支持",
    "REJECTED": "不支持",
    "INCONCLUSIVE": "证据不足",
}
DECIDED_VERDICTS = {"CONFIRMED", "REJECTED", "INCONCLUSIVE"}


class EvidenceError(ValueError):
    pass


def claim_out(row: ProjectEvidenceClaim) -> ProjectEvidenceClaimOut:
    return ProjectEvidenceClaimOut(
        id=row.id,
        project_id=row.project_id,
        claim=row.claim,
        counterevidence=row.counterevidence,
        evidence_level=row.evidence_level,
        evidence_level_label=EVIDENCE_LEVEL_LABELS.get(row.evidence_level, row.evidence_level),
        evidence_type=row.evidence_type,
        evidence_type_label=EVIDENCE_TYPE_LABELS.get(row.evidence_type, row.evidence_type),
        gate_condition_id=row.gate_condition_id,
        source_description=row.source_description,
        source_url=row.source_url,
        sample_scope=row.sample_scope,
        finding=row.finding,
        verdict=row.verdict,
        verdict_label=VERDICT_LABELS.get(row.verdict, row.verdict),
        decision_note=row.decision_note,
        created_by_user_id=row.created_by_user_id,
        created_by=row.created_by.display_name if row.created_by else None,
        decided_by_user_id=row.decided_by_user_id,
        decided_by=row.decided_by.display_name if row.decided_by else None,
        created_at=row.created_at,
        decided_at=row.decided_at,
    )


def list_claims(db: Session, project_id: int) -> List[ProjectEvidenceClaimOut]:
    rows = db.scalars(
        select(ProjectEvidenceClaim)
        .options(
            joinedload(ProjectEvidenceClaim.created_by),
            joinedload(ProjectEvidenceClaim.decided_by),
        )
        .where(ProjectEvidenceClaim.project_id == project_id)
        .order_by(ProjectEvidenceClaim.created_at, ProjectEvidenceClaim.id)
    ).all()
    return [claim_out(row) for row in rows]


def create_claim(db: Session, project_id: int, data: dict, user) -> ProjectEvidenceClaim:
    row = ProjectEvidenceClaim(
        project_id=project_id,
        **data,
        verdict="PENDING",
        created_by_user_id=user.id,
    )
    db.add(row)
    db.flush()
    return row


def decide_claim(
    db: Session, row: ProjectEvidenceClaim, verdict: str, decision_note: str | None, user
) -> ProjectEvidenceClaim:
    if row.verdict != "PENDING":
        raise EvidenceError("裁决记录不可覆盖；如需复核，请新增证据记录")
    if verdict not in DECIDED_VERDICTS:
        raise EvidenceError("裁决必须选择支持、不支持或证据不足")
    if row.created_by_user_id == user.id:
        raise EvidenceError("裁决必须由非主张创建人独立复核")
    if not (decision_note or "").strip():
        raise EvidenceError("裁决必须填写判断依据")
    if verdict == "CONFIRMED" and row.evidence_level not in {"L1", "L2", "L3"}:
        raise EvidenceError("仅有 L4-L5 证据的主张只能标记待验证，不能进入执行判断")

    row.verdict = verdict
    row.decision_note = decision_note.strip()
    row.decided_by_user_id = user.id
    row.decided_at = utcnow()
    db.flush()
    return row


def root_cause_evidence_ready(db: Session, project_id: int, condition_id: int) -> bool:
    """根因门只认显式绑定到该门条件的、已独立裁决的 L1-L3 证据。"""
    rows = db.scalars(
        select(ProjectEvidenceClaim).where(
            ProjectEvidenceClaim.project_id == project_id,
            ProjectEvidenceClaim.gate_condition_id == condition_id,
            ProjectEvidenceClaim.verdict == "CONFIRMED",
            ProjectEvidenceClaim.evidence_level.in_(("L1", "L2", "L3")),
        )
    ).all()
    evidence_types_by_claim: Dict[str, set[str]] = defaultdict(set)
    for row in rows:
        key = " ".join(row.claim.casefold().split())
        evidence_types_by_claim[key].add(row.evidence_type.casefold().strip())
    return any(len(types) >= 2 for types in evidence_types_by_claim.values())
