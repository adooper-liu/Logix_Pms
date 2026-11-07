"""Public sandbox management remains off by default and enforces write roles."""


def test_engine_management_routes_default_off_and_viewer_denied(client, viewer_client):
    response = client.get("/api/v1/execution/engine/status?process_id=1")
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    response = viewer_client.post("/api/v1/execution/engine/deploy", json={"model_version_id": 1})
    assert response.status_code == 403
