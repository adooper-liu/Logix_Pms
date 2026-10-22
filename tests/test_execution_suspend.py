"""流程实例挂起/恢复：任务阻断、升级跳过与权限。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _start(client, code: str = "L3-032") -> dict:
    response = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client, code)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _open_task(client, instance_id: int) -> dict:
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    assert tasks
    return tasks[0]


def _assignee_id(client, display_name: str) -> int:
    rows = client.get(f"{API}/execution/assignees").json()
    return next(row["id"] for row in rows if row["display_name"] == display_name)


def _save_config(client, process_id: int, **values) -> None:
    payload = {
        "default_task_due_hours": None,
        "default_escalation_hours": None,
        "default_escalation_user_id": None,
    }
    payload.update(values)
    response = client.put(
        f"{API}/execution/config", params={"process_id": process_id}, json=payload
    )
    assert response.status_code == 200, response.text


def test_suspend_blocks_tasks_and_resume_restores(manager_client, owner_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        suspended = manager_client.post(
            f"{API}/execution/instances/{iid}/suspend",
            json={"reason": "年度盘点"},
        )
        assert suspended.status_code == 200, suspended.text
        body = suspended.json()
        assert body["status"] == "SUSPENDED"
        assert body["status_label"] == "已挂起"
        assert body["suspend_reason"] == "年度盘点"
        assert body["suspended_at"] is not None

        denied = owner_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert denied.status_code == 409, denied.text
        assert "挂起" in denied.json()["detail"]

        denied_manager = manager_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert denied_manager.status_code == 409, denied_manager.text

        resumed = manager_client.post(f"{API}/execution/instances/{iid}/resume")
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()["status"] == "RUNNING"
        assert resumed.json()["suspended_at"] is None
        assert resumed.json()["suspend_reason"] is None

        claimed = owner_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert claimed.status_code == 200, claimed.text
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_suspended_task_is_not_escalated(manager_client):
    process_id = _process_id(manager_client)
    chen_id = _assignee_id(manager_client, "陈经理")
    original = manager_client.get(
        f"{API}/execution/config", params={"process_id": process_id}
    ).json()
    instance = None
    try:
        _save_config(
            manager_client,
            process_id,
            default_task_due_hours=0,
            default_escalation_hours=0,
            default_escalation_user_id=chen_id,
        )
        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        manager_client.post(f"{API}/execution/instances/{instance['id']}/suspend", json={})

        paused = manager_client.post(
            f"{API}/execution/escalations/scan", params={"process_id": process_id}
        ).json()
        assert task["id"] not in paused["task_ids"]
        current = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert current["escalated_at"] is None

        manager_client.post(f"{API}/execution/instances/{instance['id']}/resume")
        resumed = manager_client.post(
            f"{API}/execution/escalations/scan", params={"process_id": process_id}
        ).json()
        assert task["id"] in resumed["task_ids"]
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        _save_config(
            manager_client,
            process_id,
            default_task_due_hours=original["default_task_due_hours"],
            default_escalation_hours=original["default_escalation_hours"],
            default_escalation_user_id=original["default_escalation_user_id"],
        )


def test_suspend_permissions_and_state_guards(manager_client, owner_client, viewer_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        assert (
            viewer_client.post(f"{API}/execution/instances/{iid}/suspend", json={}).status_code
            == 403
        )
        assert (
            owner_client.post(f"{API}/execution/instances/{iid}/suspend", json={}).status_code
            == 403
        )
        assert manager_client.post(f"{API}/execution/instances/{iid}/resume").status_code == 409

        manager_client.post(f"{API}/execution/instances/{iid}/suspend", json={})
        assert (
            manager_client.post(f"{API}/execution/instances/{iid}/suspend", json={}).status_code
            == 409
        )
        cancelled = manager_client.post(f"{API}/execution/instances/{iid}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        assert cancelled.json()["status"] == "CANCELLED"
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")
