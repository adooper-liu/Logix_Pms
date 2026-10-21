"""ERP/OA 集成：端点 CRUD、Outbox 投递、签名、重试与事件过滤。"""

from __future__ import annotations

from app.services import integrations as integration_service

API = "/api/v1"


def _process_id(client) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(r["id"] for r in rows if r["code"] == "L3-032")


def _create_endpoint(client, code: str, events: list, active: bool = True) -> dict:
    r = client.post(
        f"{API}/integrations/endpoints",
        json={
            "code": code,
            "name": "测试端点",
            "kind": "WEBHOOK",
            "url": "https://example.com/hooks/logix",
            "secret": "test-secret",
            "events": events,
            "is_active": active,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _deliveries(client, **params) -> list:
    return client.get(f"{API}/integrations/deliveries", params=params).json()


def test_seed_endpoint_and_permissions(manager_client, viewer_client):
    rows = manager_client.get(f"{API}/integrations/endpoints").json()
    assert any(row["code"] == "ERP-DEMO" and not row["is_active"] for row in rows)
    assert viewer_client.get(f"{API}/integrations/endpoints").status_code == 200
    assert (
        viewer_client.post(
            f"{API}/integrations/endpoints",
            json={
                "code": "VIEWER-HOOK",
                "name": "只读不该建",
                "url": "https://example.com/hook",
            },
        ).status_code
        == 403
    )


def test_endpoint_validation(manager_client):
    bad_url = manager_client.post(
        f"{API}/integrations/endpoints",
        json={"code": "BAD-URL", "name": "坏 URL", "url": "ftp://example.com"},
    )
    assert bad_url.status_code == 400
    assert "http" in bad_url.json()["detail"]

    bad_event = manager_client.post(
        f"{API}/integrations/endpoints",
        json={
            "code": "BAD-EVENT",
            "name": "坏事件",
            "url": "https://example.com/hook",
            "events": ["not.an.event"],
        },
    )
    assert bad_event.status_code == 400
    assert "未知事件" in bad_event.json()["detail"]


def test_enqueue_and_deliver_with_signature(manager_client, monkeypatch):
    endpoint = _create_endpoint(manager_client, "TEST-HOOK", ["instance.started"])
    calls = []

    def fake_post(url, body, headers, timeout=5):
        calls.append((url, body, headers))
        return 200, None

    monkeypatch.setattr(integration_service, "_post_json", fake_post)
    instance = manager_client.post(
        f"{API}/execution/instances", json={"process_id": _process_id(manager_client)}
    ).json()
    try:
        rows = [d for d in _deliveries(manager_client) if d["endpoint_id"] == endpoint["id"]]
        assert len(rows) == 1
        assert rows[0]["event_type"] == "instance.started"
        assert rows[0]["status"] == "PENDING"

        run = manager_client.post(f"{API}/integrations/deliveries/run")
        assert run.status_code == 200, run.text
        assert run.json()["delivered"] >= 1

        done = [
            d
            for d in _deliveries(manager_client, status="SUCCESS")
            if d["endpoint_id"] == endpoint["id"]
        ]
        assert done and done[0]["delivered_at"]
        assert calls, "应实际调用 webhook"
        _, body, headers = calls[0]
        assert '"instance.started"' in body
        assert headers["X-Logix-Event"] == "instance.started"
        assert headers["X-Logix-Signature"].startswith("sha256=")
    finally:
        manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.delete(f"{API}/integrations/endpoints/{endpoint['id']}")


def test_failure_backoff_and_manual_retry(manager_client, monkeypatch):
    endpoint = _create_endpoint(manager_client, "FAIL-HOOK", ["instance.started"])
    instance = manager_client.post(
        f"{API}/execution/instances", json={"process_id": _process_id(manager_client)}
    ).json()
    try:

        def fail_post(url, body, headers, timeout=5):
            return 500, "HTTP 500: boom"

        monkeypatch.setattr(integration_service, "_post_json", fail_post)
        first = manager_client.post(f"{API}/integrations/deliveries/run").json()
        assert first["processed"] >= 1
        delivery = next(
            d for d in _deliveries(manager_client) if d["endpoint_id"] == endpoint["id"]
        )
        assert delivery["status"] == "PENDING", "未到 3 次前应保留重试机会"
        assert delivery["attempts"] == 1
        assert delivery["error"] and "boom" in delivery["error"]
        assert delivery["next_attempt_at"]

        # 未到退避时间，不应再次投递
        second = manager_client.post(f"{API}/integrations/deliveries/run").json()
        assert second["processed"] == 0

        retried = manager_client.post(f"{API}/integrations/deliveries/{delivery['id']}/retry")
        assert retried.status_code == 200
        assert retried.json()["attempts"] == 0
        assert retried.json()["next_attempt_at"] is None

        def ok_post(url, body, headers, timeout=5):
            return 204, None

        monkeypatch.setattr(integration_service, "_post_json", ok_post)
        assert manager_client.post(f"{API}/integrations/deliveries/run").status_code == 200
        final = next(
            d
            for d in _deliveries(manager_client, status="SUCCESS")
            if d["endpoint_id"] == endpoint["id"]
        )
        assert final["delivered_at"]
    finally:
        manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.delete(f"{API}/integrations/endpoints/{endpoint['id']}")


def test_event_subscription_filters(manager_client, monkeypatch):
    endpoint = _create_endpoint(manager_client, "COMPLETE-HOOK", ["task.completed"])
    calls = []

    def fake_post(url, body, headers, timeout=5):
        calls.append((url, body, headers))
        return 200, None

    monkeypatch.setattr(integration_service, "_post_json", fake_post)
    instance = manager_client.post(
        f"{API}/execution/instances", json={"process_id": _process_id(manager_client)}
    ).json()
    try:
        rows = [d for d in _deliveries(manager_client) if d["endpoint_id"] == endpoint["id"]]
        assert rows == [], "只订阅 task.completed 的端点不应收到 instance.started"

        task = manager_client.get(
            f"{API}/execution/tasks",
            params={"instance_id": instance["id"], "only_open": True},
        ).json()[0]
        manager_client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={"form_data": {"applicant": "集成测试", "amount": 1}},
        )
        rows = [d for d in _deliveries(manager_client) if d["endpoint_id"] == endpoint["id"]]
        assert rows and rows[0]["event_type"] == "task.completed"
    finally:
        manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.delete(f"{API}/integrations/endpoints/{endpoint['id']}")


def test_exception_event_enqueued(manager_client):
    endpoint = _create_endpoint(manager_client, "EXC-HOOK", ["exception.created"])
    created = manager_client.post(
        f"{API}/monitor/exceptions", json={"title": "集成事件测试", "severity": "LOW"}
    ).json()
    try:
        rows = [d for d in _deliveries(manager_client) if d["endpoint_id"] == endpoint["id"]]
        assert rows and rows[0]["event_type"] == "exception.created"
        assert rows[0]["payload"]["code"] == created["code"]
    finally:
        manager_client.delete(f"{API}/monitor/exceptions/{created['id']}")
        manager_client.delete(f"{API}/integrations/endpoints/{endpoint['id']}")


def test_viewer_cannot_run_deliveries(viewer_client):
    assert viewer_client.post(f"{API}/integrations/deliveries/run").status_code == 403
