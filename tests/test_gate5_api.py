"""Generic Gate 5 API contracts."""


def test_gate5_readiness_route_is_registered_and_generic(client):
    rows = client.get("/api/v1/process-map/flat").json()
    process = next(row for row in rows if row["level"] == 3)
    response = client.get(f"/api/v1/processes/{process['id']}/gate5/readiness")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["process_id"] == process["id"]
    assert body["process_code"] == process["code"]
    assert "blockers" in body and "activities" in body


def test_gate5_write_routes_reject_viewer(viewer_client):
    rows = viewer_client.get("/api/v1/process-map/flat").json()
    process = next(row for row in rows if row["level"] == 3)
    response = viewer_client.put(
        f"/api/v1/processes/{process['id']}/gate5/owner",
        json={"expected_model_version_id": 1, "owner_user_id": 1},
    )
    assert response.status_code == 403


def test_gate5_readiness_does_not_create_gate_assessment(client):
    from app.core.database import SessionLocal
    from app.models.process_operating import ProcessGateAssessment

    process = next(
        row for row in client.get("/api/v1/process-map/flat").json() if row["level"] == 3
    )
    with SessionLocal() as db:
        before = db.query(ProcessGateAssessment).count()
    response = client.get(f"/api/v1/processes/{process['id']}/gate5/readiness")
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.query(ProcessGateAssessment).count() == before
