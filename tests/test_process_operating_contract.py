"""Generic process operating contract and L3-032 sample integration tests."""

import pytest


@pytest.fixture
def db_session():
    from app.core.database import Base, SessionLocal, engine

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        yield db
        db.rollback()


@pytest.fixture
def temporary_process(db_session):
    from uuid import uuid4

    from app.models.process import ProcessArch

    process = ProcessArch(
        code=f"L3-CONTRACT-{uuid4().hex[:8]}",
        name="流程经营契约测试流程",
        level=3,
    )
    db_session.add(process)
    db_session.flush()
    yield process


@pytest.fixture
def operating_cycle(db_session, temporary_process):
    from app.services.process_operating import create_cycle

    return create_cycle(db_session, process_id=temporary_process.id, cycle_type="BASELINE")


def test_contract_is_keyed_by_any_l3_not_sample_code(db_session, temporary_process):
    from app.services.process_operating import create_cycle

    cycle = create_cycle(db_session, process_id=temporary_process.id, cycle_type="BASELINE")
    assert cycle.process_id == temporary_process.id
    assert cycle.process_id != 3


def test_cycle_history_preserves_superseded_cycle(db_session, operating_cycle):
    from app.services.process_operating import activate_cycle, create_cycle

    first = create_cycle(db_session, process_id=operating_cycle.process_id, cycle_type="PILOT")
    activate_cycle(db_session, first.id)
    second = create_cycle(
        db_session,
        process_id=operating_cycle.process_id,
        cycle_type="PILOT",
        supersedes_cycle_id=first.id,
    )
    activate_cycle(db_session, second.id)
    db_session.refresh(first)
    assert first.status == "SUPERSEDED"
    assert second.status == "ACTIVE"
    assert second.supersedes_cycle_id == first.id


def test_gate_12_is_not_required_for_first_launch(db_session):
    from app.services.process_operating import can_enter_launch, can_enter_pilot

    gates = {f"GATE_{number}": "PASS" for number in range(1, 11)}
    assert can_enter_pilot(gates) is True
    gates["GATE_11"] = "PASS"
    assert can_enter_launch(gates) is True


def test_gate_7_and_gate_9_support_not_applicable_and_rigor(db_session, operating_cycle):
    from app.services.process_operating import assess_gate

    gate = assess_gate(
        db_session,
        cycle_id=operating_cycle.id,
        gate_key="GATE_9",
        status="NOT_STARTED",
        applicability="NOT_APPLICABLE",
        rigor="LIGHT",
        applicability_reason="本周期不做组织扩编决策",
    )
    assert gate.applicability == "NOT_APPLICABLE"
    assert gate.rigor == "LIGHT"
    assert gate.does_not_block_launch is True


def test_seed_configuration_is_not_business_evidence(db_session, operating_cycle):
    from app.services.process_operating import add_evidence, assess_gate

    gate = assess_gate(db_session, cycle_id=operating_cycle.id, gate_key="GATE_4")
    seed = add_evidence(
        db_session,
        gate_assessment_id=gate.id,
        source_type="SEED_CONFIGURATION",
        source_id="seed-process-node",
    )
    real = add_evidence(
        db_session,
        gate_assessment_id=gate.id,
        source_type="REAL_BUSINESS_RUN",
        source_id="instance-001",
    )
    assert seed.evidence_grade == "E1"
    assert real.evidence_grade == "E3"


def test_decision_uses_process_specific_authorizer(db_session, operating_cycle):
    from app.services.process_operating import record_decision

    decision = record_decision(
        db_session,
        cycle_id=operating_cycle.id,
        decision_type="APPROVE_LAUNCH",
        decision="APPROVED",
        decision_by_user_id=88,
        authority_basis="PROCESS_SPECIFIC_AUTHORIZER",
    )
    assert decision.decision_by_user_id == 88
    assert decision.authority_basis == "PROCESS_SPECIFIC_AUTHORIZER"


def test_sample_summary_accepts_any_l3_and_does_not_create_state(db_session, temporary_process):
    from app.models.process_operating import ProcessOperatingCycle
    from app.services.process_operating_summary import sample_operating_summary

    before = db_session.query(ProcessOperatingCycle).count()
    summary = sample_operating_summary(db_session, temporary_process.id)
    assert summary["process_id"] == temporary_process.id
    assert summary["cycle_id"] is None
    assert summary["can_enter_pilot"] is False
    assert summary["sample_only"] is True
    assert db_session.query(ProcessOperatingCycle).count() == before


def test_sample_l3_032_summary_reports_missing_operating_cycle(client, db_session):
    from app.services.process_operating_summary import sample_operating_summary

    rows = client.get("/api/v1/process-map/flat").json()
    sample = next(row for row in rows if row["code"] == "L3-032")
    summary = sample_operating_summary(db_session, sample["id"])
    assert summary["process_id"] == sample["id"]
    assert summary["next_action"] == "创建流程经营周期并确认目标与结果"
    assert summary["blocking_gates"] == ["GATE_1"]
