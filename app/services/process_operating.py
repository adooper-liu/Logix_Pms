"""Generic process operating contract service."""

from __future__ import annotations

from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.timeutil import utcnow
from app.models.process_operating import (
    ProcessGateAssessment,
    ProcessGateEvidence,
    ProcessOperatingCycle,
    ProcessOperatingDecision,
)


def create_cycle(
    db: Session,
    *,
    process_id: int,
    cycle_type: str,
    project_id: int | None = None,
    model_version_id: int | None = None,
    supersedes_cycle_id: int | None = None,
) -> ProcessOperatingCycle:
    cycle = ProcessOperatingCycle(
        process_id=process_id,
        cycle_type=cycle_type,
        project_id=project_id,
        model_version_id=model_version_id,
        supersedes_cycle_id=supersedes_cycle_id,
        status="DRAFT",
    )
    db.add(cycle)
    db.flush()
    return cycle


def activate_cycle(db: Session, cycle_id: int) -> ProcessOperatingCycle:
    cycle = db.get(ProcessOperatingCycle, cycle_id)
    if cycle is None:
        raise ValueError("经营周期不存在")
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
    grade = "E3" if source_type == "REAL_BUSINESS_RUN" else "E1"
    evidence = ProcessGateEvidence(
        gate_assessment_id=gate_assessment_id,
        source_type=source_type,
        source_id=source_id,
        evidence_grade=grade,
        **values,
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


def can_enter_pilot(gates: Mapping[str, str]) -> bool:
    return all(gates.get(f"GATE_{number}") in {"PASS", "NOT_APPLICABLE"} for number in range(1, 11))


def can_enter_launch(gates: Mapping[str, str]) -> bool:
    return can_enter_pilot(gates) and gates.get("GATE_11") in {"PASS", "CONDITIONAL"}
