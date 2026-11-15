"""Read-only process operating summary API contract."""


def test_operating_summary_endpoint_is_registered(client):
    rows = client.get("/api/v1/process-map/flat").json()
    process = next(row for row in rows if row["code"] == "L3-032")
    response = client.get(f"/api/v1/processes/{process['id']}/operating-summary")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["process_id"] == process["id"]
    assert body["sample_only"] is True
    assert body["cycle_id"] is None
    assert body["blocking_gates"] == ["GATE_1"]
    assert body["next_action"] == "创建流程经营周期并确认目标与结果"


def test_operating_summary_active_cycle_reports_unverified_evidence(client):
    from app.core.database import SessionLocal
    from app.models.process_operating import ProcessOperatingCycle
    from app.services.process_operating import (
        activate_cycle,
        add_evidence,
        assess_gate,
        create_cycle,
    )

    process = next(
        row for row in client.get("/api/v1/process-map/flat").json() if row["level"] == 3
    )
    with SessionLocal() as db:
        cycle = create_cycle(db, process_id=process["id"], cycle_type="BASELINE")
        activate_cycle(db, cycle.id)
        gate = assess_gate(db, cycle_id=cycle.id, gate_key="GATE_4", status="PASS")
        add_evidence(
            db, gate_assessment_id=gate.id, source_type="REAL_BUSINESS_RUN", source_id="unverified"
        )
        db.commit()
    try:
        response = client.get(f"/api/v1/processes/{process['id']}/operating-summary")
        assert response.status_code == 200, response.text
        assert "GATE_4" in response.json()["unverified_evidence"]
    finally:
        with SessionLocal() as db:
            db.query(ProcessOperatingCycle).filter_by(id=cycle.id).delete()
            db.commit()


def test_operating_summary_rejects_non_l3(client):
    rows = client.get("/api/v1/process-map/flat").json()
    activity = next(row for row in rows if row["level"] == 4)
    response = client.get(f"/api/v1/processes/{activity['id']}/operating-summary")

    assert response.status_code == 422
