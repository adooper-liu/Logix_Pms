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


def test_operating_summary_rejects_non_l3(client):
    rows = client.get("/api/v1/process-map/flat").json()
    activity = next(row for row in rows if row["level"] == 4)
    response = client.get(f"/api/v1/processes/{activity['id']}/operating-summary")

    assert response.status_code == 422
