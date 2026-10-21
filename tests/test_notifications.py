"""通知：未读数、已读、逾期扫描与执行事件通知。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(r["id"] for r in rows if r["code"] == code)


def _click_all_read(client) -> None:
    # 直接用 API 把该用户的未读清零，避免测试间互相影响
    rows = client.get(f"{API}/notifications?unread_only=true&limit=200").json()
    for row in rows:
        client.post(f"{API}/notifications/{row['id']}/read")


def test_seed_notifications_and_read_flow(owner_client):
    summary = owner_client.get(f"{API}/notifications/summary").json()
    assert summary["unread"] >= 2
    assert "TASK_ASSIGNED" in summary["by_type"]
    assert "EXCEPTION_OVERDUE" in summary["by_type"]

    items = owner_client.get(f"{API}/notifications", params={"limit": 50}).json()
    assert items
    unread_before = sum(1 for n in items if not n["is_read"])
    first = next(n for n in items if not n["is_read"])
    marked = owner_client.post(f"{API}/notifications/{first['id']}/read")
    assert marked.status_code == 200
    assert marked.json()["is_read"] is True
    after = owner_client.get(f"{API}/notifications/summary").json()
    assert after["unread"] == max(0, unread_before - 1)

    assert owner_client.post(f"{API}/notifications/read-all").status_code == 200
    assert owner_client.get(f"{API}/notifications/summary").json()["unread"] == 0


def test_viewer_cannot_scan(viewer_client):
    assert viewer_client.post(f"{API}/notifications/scan").status_code == 403


def test_scan_overdue_is_deduplicated(manager_client, owner_client):
    _click_all_read(owner_client)
    first = manager_client.post(f"{API}/notifications/scan")
    assert first.status_code == 200, first.text
    assert first.json()["created"] >= 1
    second = manager_client.post(f"{API}/notifications/scan")
    assert second.status_code == 200
    assert second.json()["created"] == 0, "同一未读提醒不应重复生成"

    summary = owner_client.get(f"{API}/notifications/summary").json()
    assert summary["unread"] >= 1


def test_task_assignment_notifies_assignee(client, owner_client):
    chen_id = owner_client.get(f"{API}/auth/me").json()["id"]
    before = owner_client.get(f"{API}/notifications/summary").json()["unread"]
    instance = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client), "assignments": {"n1": chen_id}},
    ).json()
    try:
        assert instance["open_task_count"] == 1
        after = owner_client.get(f"{API}/notifications/summary").json()["unread"]
        assert after > before
        items = owner_client.get(f"{API}/notifications?limit=50").json()
        hit = next(
            n
            for n in items
            if n["type"] == "TASK_ASSIGNED"
            and n["entity_id"] is not None
            and n["entity_type"] == "process_task"
        )
        assert "需求发起" in hit["title"]
    finally:
        client.delete(f"{API}/execution/instances/{instance['id']}")


def test_instance_completion_notifies_starter(client):
    instance = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client)},
    ).json()
    iid = instance["id"]
    try:
        # n1 → n2 → n3 → n4 → n5 → 完成
        for step in range(3):
            task = client.get(
                f"{API}/execution/tasks",
                params={"instance_id": iid, "only_open": True},
            ).json()[0]
            data = {"applicant": "通知测试", "amount": 100} if step == 0 else None
            assert (
                client.post(
                    f"{API}/execution/tasks/{task['id']}/complete",
                    json={"form_data": data},
                ).status_code
                == 200
            )
        n4 = client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        assert n4["node_key"] == "n4"
        assert (
            client.post(
                f"{API}/execution/tasks/{n4['id']}/complete",
                json={"form_data": {"approved": "是"}},
            ).status_code
            == 200
        )
        n5 = client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        assert client.post(f"{API}/execution/tasks/{n5['id']}/complete", json={}).status_code == 200

        items = client.get(f"{API}/notifications?limit=100").json()
        hit = next(n for n in items if n["type"] == "INSTANCE_COMPLETED" and n["entity_id"] == iid)
        assert "流程已完成" in hit["title"]
    finally:
        client.delete(f"{API}/execution/instances/{iid}")
