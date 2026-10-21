"""流程执行：实例、任务队列、分支、权限与闭环。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _start(client, code: str = "L3-032") -> dict:
    r = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client, code), "variables": {"case": "test"}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _open_task(client, instance_id: int) -> dict:
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    assert tasks, f"实例 {instance_id} 没有待办任务"
    return tasks[0]


def _complete(client, task_id: int, **payload) -> dict:
    r = client.post(f"{API}/execution/tasks/{task_id}/complete", json=payload)
    return r


# ------------------------------------------------------------------ 基础


def test_executable_processes(client):
    rows = client.get(f"{API}/execution/processes").json()
    codes = {r["code"] for r in rows}
    assert {"L3-032", "L3-033"} <= codes
    by_code = {r["code"]: r for r in rows}
    assert by_code["L3-032"]["node_count"] == 6
    assert by_code["L3-033"]["node_count"] >= 5


def test_start_requires_login(anon_client):
    assert anon_client.get(f"{API}/execution/processes").status_code == 401
    assert anon_client.get(f"{API}/execution/tasks").status_code == 401


def test_seeded_instances_and_queue(client):
    instances = client.get(f"{API}/execution/instances").json()
    assert len(instances) >= 2
    assert all(i["status"] in ("RUNNING", "COMPLETED") for i in instances)

    tasks = client.get(f"{API}/execution/tasks", params={"only_open": True}).json()
    assert len(tasks) >= 2
    assert any(t["assignee_name"] for t in tasks), "种子数据应有一条已指派任务"
    assert any(t["assignee_user_id"] is None for t in tasks), "种子数据应有一条公共队列任务"


# ------------------------------------------------------------------ 主流程


def test_start_complete_branch_and_finish(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        assert task["node_key"] == "n1"
        assert task["next_options"][0]["node_key"] == "n2"

        claimed = client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert claimed.status_code == 200
        assert claimed.json()["status"] == "CLAIMED"
        assert claimed.json()["assignee_user_id"] is not None

        # n1 → n2 → n3 → n4，每步只有一条出边
        for _ in range(3):
            task = _open_task(client, iid)
            done = _complete(client, task["id"], form_data={"node": task["node_key"]})
            assert done.status_code == 200, done.text

        # n4 是审批分支：不指定下一步应拒绝
        n4 = _open_task(client, iid)
        assert n4["node_key"] == "n4"
        assert {o["node_key"] for o in n4["next_options"]} == {"n5", "n6"}
        rejected = _complete(client, n4["id"])
        assert rejected.status_code == 400
        assert "多个分支" in rejected.json()["detail"]

        # 选择通过 → n5；n5 无出边 → 实例完成
        assert _complete(client, n4["id"], next_node_key="n5").status_code == 200
        n5 = _open_task(client, iid)
        assert n5["node_key"] == "n5"
        assert _complete(client, n5["id"], comment="完成").status_code == 200

        detail = client.get(f"{API}/execution/instances/{iid}").json()
        assert detail["instance"]["status"] == "COMPLETED"
        assert detail["instance"]["open_task_count"] == 0
        assert detail["instance"]["current_node_key"] is None
        assert [t["node_key"] for t in detail["tasks"]] == ["n1", "n2", "n3", "n4", "n5"]
        assert all(t["status"] == "COMPLETED" for t in detail["tasks"])
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


def test_branch_back_to_previous_step_creates_new_task(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        for _ in range(3):
            task = _open_task(client, iid)
            assert _complete(client, task["id"]).status_code == 200
        n4 = _open_task(client, iid)
        assert n4["node_key"] == "n4"
        assert _complete(client, n4["id"], next_node_key="n6").status_code == 200

        n6 = _open_task(client, iid)
        assert n6["node_key"] == "n6"
        assert _complete(client, n6["id"]).status_code == 200

        # n6 → n2，产生新的 n2 任务
        again = _open_task(client, iid)
        assert again["node_key"] == "n2"
        assert again["id"] != n6["id"]
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


# ------------------------------------------------------------------ 权限与改派


def test_owner_can_claim_and_complete_unassigned_task(owner_client):
    instance = _start(owner_client)
    iid = instance["id"]
    try:
        task = _open_task(owner_client, iid)
        assert task["assignee_user_id"] is None
        done = _complete(owner_client, task["id"], form_data={"by": "owner"})
        assert done.status_code == 200
        assert done.json()["assignee_name"] == "陈经理"
    finally:
        owner_client.delete(f"{API}/execution/instances/{iid}")


def test_viewer_cannot_claim_or_complete(viewer_client):
    task = viewer_client.get(f"{API}/execution/tasks", params={"only_open": True}).json()[0]
    assert viewer_client.post(f"{API}/execution/tasks/{task['id']}/claim").status_code == 403
    assert (
        viewer_client.post(f"{API}/execution/tasks/{task['id']}/complete", json={}).status_code
        == 403
    )


def test_manager_can_reassign_task(manager_client, owner_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        chen_id = owner_client.get(f"{API}/auth/me").json()["id"]
        assigned = manager_client.patch(
            f"{API}/execution/tasks/{task['id']}/assignee",
            json={"assignee_user_id": chen_id},
        )
        assert assigned.status_code == 200
        assert assigned.json()["assignee_user_id"] == chen_id
        assert assigned.json()["status"] == "CLAIMED"

        # 已指派给陈经理后，管理员不能再以普通身份处理（管理员本身有管理权限，允许）
        assert _complete(manager_client, task["id"]).status_code == 200

        # 退回公共队列
        next_task = _open_task(manager_client, iid)
        cleared = manager_client.patch(
            f"{API}/execution/tasks/{next_task['id']}/assignee",
            json={"assignee_user_id": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["status"] == "PENDING"
        assert cleared.json()["assignee_user_id"] is None
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


# ------------------------------------------------------------------ 取消 / 删除 / 审计


def test_cancel_instance_cancels_open_tasks(manager_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        cancelled = manager_client.post(f"{API}/execution/instances/{iid}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["open_task_count"] == 0

        # 已取消的实例不能再处理任务
        detail = manager_client.get(f"{API}/execution/instances/{iid}").json()
        assert all(t["status"] == "CANCELLED" for t in detail["tasks"])
        assert (
            manager_client.post(
                f"{API}/execution/tasks/{detail['tasks'][0]['id']}/complete", json={}
            ).status_code
            == 409
        )
        assert manager_client.post(f"{API}/execution/instances/{iid}/cancel").status_code == 409
    finally:
        assert manager_client.delete(f"{API}/execution/instances/{iid}").status_code == 200
        assert manager_client.get(f"{API}/execution/instances/{iid}").status_code == 404


def test_execution_writes_are_audited(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        client.post(f"{API}/execution/tasks/{task['id']}/claim")
        client.post(f"{API}/execution/tasks/{task['id']}/complete", json={})
    finally:
        client.delete(f"{API}/execution/instances/{iid}")

    logs = client.get(f"{API}/audit", params={"entity_type": "process_task", "limit": 100}).json()
    assert logs["total"] >= 2
    assert any(i["entity_id"] == task["id"] for i in logs["items"])

    instance_logs = client.get(
        f"{API}/audit", params={"entity_type": "process_instance", "limit": 100}
    ).json()
    assert any(i["entity_id"] == iid for i in instance_logs["items"])
