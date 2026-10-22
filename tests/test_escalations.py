"""超期任务自动升级：流程默认、节点覆盖、快照冻结与幂等。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _start(client, code: str = "L3-032") -> dict:
    response = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client, code), "variables": {"case": "escalation"}},
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


def _user_id(client, username: str) -> int:
    rows = client.get(f"{API}/auth/users", params={"keyword": username}).json()
    return next(row["id"] for row in rows if row["username"] == username)


def _config(client, process_id: int) -> dict:
    return client.get(f"{API}/execution/config", params={"process_id": process_id}).json()


def _save_config(client, process_id: int, **values) -> dict:
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
    return response.json()


def _restore_config(client, process_id: int, original: dict) -> None:
    _save_config(
        client,
        process_id,
        default_task_due_hours=original["default_task_due_hours"],
        default_escalation_hours=original["default_escalation_hours"],
        default_escalation_user_id=original["default_escalation_user_id"],
    )


def _scan(client, process_id: int) -> dict:
    response = client.post(f"{API}/execution/escalations/scan", params={"process_id": process_id})
    assert response.status_code == 200, response.text
    return response.json()


def test_process_escalation_uses_start_snapshot(manager_client, client):
    process_id = _process_id(manager_client)
    chen_id = _assignee_id(manager_client, "陈经理")
    admin_id = _user_id(client, "admin")
    original = _config(manager_client, process_id)
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
        assert task["due_at"] and task["assignee_user_id"] is None
        assert task["escalated_at"] is None

        # 启动后再改配置，不应影响已启动实例（快照冻结）
        _save_config(
            manager_client,
            process_id,
            default_task_due_hours=0,
            default_escalation_hours=0,
            default_escalation_user_id=admin_id,
        )
        result = _scan(manager_client, process_id)
        assert result["escalated"] >= 1
        assert task["id"] in result["task_ids"]

        escalated = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert escalated["assignee_user_id"] == chen_id
        assert escalated["assignee_name"] == "陈经理"
        assert escalated["escalated_at"] is not None
        assert escalated["escalated_to_name"] == "陈经理"

        # 同一任务只升级一次
        again = _scan(manager_client, process_id)
        assert task["id"] not in again["task_ids"]
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        _restore_config(manager_client, process_id, original)


def test_node_assignment_overrides_escalation(manager_client, client):
    process_id = _process_id(manager_client)
    chen_id = _assignee_id(manager_client, "陈经理")
    admin_id = _user_id(client, "admin")
    original = _config(manager_client, process_id)
    instance = None
    try:
        _save_config(
            manager_client,
            process_id,
            default_task_due_hours=0,
            default_escalation_hours=0,
            default_escalation_user_id=chen_id,
        )
        saved = manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "escalation_hours": 0,
                "escalation_user_id": admin_id,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["escalation_user_name"] == "系统管理员"

        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        result = _scan(manager_client, process_id)
        assert task["id"] in result["task_ids"]

        escalated = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert escalated["assignee_user_id"] == admin_id
        assert escalated["escalated_to_name"] == "系统管理员"
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "role": None,
                "org_unit_id": None,
                "default_assignee_user_id": None,
                "due_hours": None,
                "escalation_hours": None,
                "escalation_user_id": None,
            },
        )
        _restore_config(manager_client, process_id, original)


def test_node_escalation_hours_can_delay(manager_client):
    process_id = _process_id(manager_client)
    chen_id = _assignee_id(manager_client, "陈经理")
    original = _config(manager_client, process_id)
    instance = None
    try:
        _save_config(
            manager_client,
            process_id,
            default_task_due_hours=0,
            default_escalation_hours=0,
            default_escalation_user_id=chen_id,
        )
        manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "escalation_hours": 24,
                "escalation_user_id": chen_id,
            },
        )
        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        result = _scan(manager_client, process_id)
        assert task["id"] not in result["task_ids"], "未到节点升级时限不应升级"
        current = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert current["escalated_at"] is None
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "role": None,
                "org_unit_id": None,
                "default_assignee_user_id": None,
                "due_hours": None,
                "escalation_hours": None,
                "escalation_user_id": None,
            },
        )
        _restore_config(manager_client, process_id, original)


def test_escalation_permissions_and_validation(client, manager_client, owner_client, viewer_client):
    process_id = _process_id(manager_client)
    viewer_id = _user_id(client, "viewer")
    original = _config(manager_client, process_id)
    try:
        assert (
            viewer_client.post(
                f"{API}/execution/escalations/scan", params={"process_id": process_id}
            ).status_code
            == 403
        )
        assert (
            owner_client.post(
                f"{API}/execution/escalations/scan", params={"process_id": process_id}
            ).status_code
            == 403
        )

        bad_config = manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={
                "default_task_due_hours": 0,
                "default_escalation_hours": 0,
                "default_escalation_user_id": viewer_id,
            },
        )
        assert bad_config.status_code == 400, bad_config.text

        bad_assignment = manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "escalation_user_id": viewer_id,
            },
        )
        assert bad_assignment.status_code == 400, bad_assignment.text

        missing = manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={
                "default_task_due_hours": 0,
                "default_escalation_hours": 0,
                "default_escalation_user_id": 999999,
            },
        )
        assert missing.status_code == 400, missing.text
    finally:
        _restore_config(manager_client, process_id, original)
