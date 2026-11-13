"""Generic process operating contract service."""

from __future__ import annotations

from datetime import datetime
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process import ProcessArch
from app.models.process_operating import (
    ProcessGateAssessment,
    ProcessGateEvidence,
    ProcessOperatingCycle,
    ProcessOperatingDecision,
)
from app.models.user import User


def create_cycle(
    db: Session,
    *,
    process_id: int,
    cycle_type: str,
    project_id: int | None = None,
    model_version_id: int | None = None,
    supersedes_cycle_id: int | None = None,
    launch_authorizer_user_id: int | None = None,
) -> ProcessOperatingCycle:
    process = db.get(ProcessArch, process_id)
    if process is None or process.level != 3:
        raise ValueError("经营周期必须关联 L3 流程")
    if project_id is not None:
        from app.models.project import Project

        project = db.get(Project, project_id)
        if project is None or project.process_id != process_id:
            raise ValueError("项目不属于该流程")
    if model_version_id is not None:
        from app.models.process import ProcessModelVersion

        version = db.get(ProcessModelVersion, model_version_id)
        if version is None or version.process_id != process_id:
            raise ValueError("模型版本不属于该流程")
    cycle = ProcessOperatingCycle(
        process_id=process_id,
        cycle_type=cycle_type,
        project_id=project_id,
        model_version_id=model_version_id,
        supersedes_cycle_id=supersedes_cycle_id,
        launch_authorizer_user_id=launch_authorizer_user_id,
        status="DRAFT",
    )
    db.add(cycle)
    db.flush()
    return cycle


def activate_cycle(db: Session, cycle_id: int) -> ProcessOperatingCycle:
    cycle = db.get(ProcessOperatingCycle, cycle_id)
    if cycle is None:
        raise ValueError("经营周期不存在")
    if cycle.status not in {"DRAFT", "ACTIVE"}:
        raise ValueError("该经营周期不允许激活")
    active = db.scalars(
        select(ProcessOperatingCycle).where(
            ProcessOperatingCycle.process_id == cycle.process_id,
            ProcessOperatingCycle.status == "ACTIVE",
            ProcessOperatingCycle.id != cycle.id,
        )
    ).all()
    for previous in active:
        previous.status = "SUPERSEDED"
        previous.closed_at = utcnow()
    cycle.status = "ACTIVE"
    cycle.started_at = cycle.started_at or utcnow()
    db.flush()
    return cycle


def assess_gate(db: Session, *, cycle_id: int, gate_key: str, **values) -> ProcessGateAssessment:
    current = db.scalar(
        select(ProcessGateAssessment).where(
            ProcessGateAssessment.cycle_id == cycle_id,
            ProcessGateAssessment.gate_key == gate_key,
            ProcessGateAssessment.is_current.is_(True),
        )
    )
    applicability = values.get("applicability", "APPLICABLE")
    if applicability == "NOT_APPLICABLE" and not values.get("applicability_reason"):
        raise ValueError("不适用必须填写理由")
    if applicability == "NOT_APPLICABLE" and gate_key not in {"GATE_7", "GATE_9"}:
        raise ValueError("该 Gate 不允许标记为不适用")
    if current is not None:
        current.is_current = False
        values["revision"] = int(current.revision or 1) + 1
    assessment = ProcessGateAssessment(cycle_id=cycle_id, gate_key=gate_key, **values)
    db.add(assessment)
    db.flush()
    return assessment


def add_evidence(
    db: Session,
    *,
    gate_assessment_id: int,
    source_type: str,
    source_id: str,
    **values,
) -> ProcessGateEvidence:
    grade = "E3" if source_type == "REAL_BUSINESS_RUN" and values.get("verified_by_user_id") else "E1"
    verification_status = "VERIFIED" if grade in {"E2", "E3", "E4"} else "UNVERIFIED"
    evidence = ProcessGateEvidence(
        gate_assessment_id=gate_assessment_id,
        source_type=source_type,
        source_id=source_id,
        evidence_grade=grade,
        verification_status=verification_status,
        verified_by_user_id=values.get("verified_by_user_id"),
        verified_at=datetime.now() if verification_status == "VERIFIED" else None,
        verification_note=values.get("verification_note"),
    )
    db.add(evidence)
    db.flush()
    return evidence


def record_decision(
    db: Session,
    *,
    cycle_id: int,
    decision_type: str,
    decision: str,
    decision_by_user_id: int,
    authority_basis: str,
    **values,
) -> ProcessOperatingDecision:
    cycle = db.get(ProcessOperatingCycle, cycle_id)
    if cycle is None:
        raise ValueError("经营周期不存在")
    user = db.get(User, decision_by_user_id)
    if user is None or not user.is_active:
        raise ValueError("决策人无效或已停用")
    if decision_type == "APPROVE_LAUNCH" and cycle.launch_authorizer_user_id != decision_by_user_id:
        raise ValueError("决策人不是该流程指定的上线授权人")
    row = ProcessOperatingDecision(
        cycle_id=cycle_id,
        decision_type=decision_type,
        decision=decision,
        decision_by_user_id=decision_by_user_id,
        authority_basis=authority_basis,
        **values,
    )
    db.add(row)
    db.flush()
    return row


def readiness(db: Session, cycle_id: int) -> dict[str, str]:
    rows = db.scalars(
        select(ProcessGateAssessment).where(
            ProcessGateAssessment.cycle_id == cycle_id,
            ProcessGateAssessment.is_current.is_(True),
        )
    ).all()
    result = {}
    for row in rows:
        evidence = db.scalars(
            select(ProcessGateEvidence).where(ProcessGateEvidence.gate_assessment_id == row.id)
        ).all()
        verified = any(item.verification_status == "VERIFIED" for item in evidence)
        result[row.gate_key] = (
            row.status if row.status in {"NOT_APPLICABLE", "CONDITIONAL"} else
            "PASS" if row.status == "PASS" and verified else "BLOCKED"
        )
    return result


def can_enter_pilot(gates: Mapping[str, str]) -> bool:
    return all(gates.get(f"GATE_{number}") in {"PASS", "NOT_APPLICABLE"} for number in range(1, 11))


def can_enter_launch(gates: Mapping[str, str]) -> bool:
    return can_enter_pilot(gates) and gates.get("GATE_11") in {"PASS", "CONDITIONAL"}
