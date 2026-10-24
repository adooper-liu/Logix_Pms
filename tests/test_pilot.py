"""十层单页：路径、层状态、待办与异常闭环。"""

from __future__ import annotations

API = "/api/v1"


def _l3(client) -> dict:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == "L3-032")


def _create_path(client, **overrides) -> dict:
    payload = {"name": "采购到付款十层试点", "process_id": _l3(client)["id"]}
    payload.update(overrides)
    created = client.post(f"{API}/pilot/paths", json=payload)
    assert created.status_code == 201, created.text
    return created.json()


def test_create_path_has_ten_layers(client):
    path = _create_path(client)
    assert path["current_layer"] == 1
    assert path["status"] == "ACTIVE"
    assert len(path["layers"]) == 10
    assert [layer["layer_no"] for layer in path["layers"]] == list(range(1, 11))
    assert path["layers"][0]["title"] == "战略与目标"
    assert path["layers"][3]["title"] == "制度与授权设计"
    assert path["layers"][0]["gate_open"] is True
    assert 0 <= path["progress"] <= 100
    layer4 = path["layers"][3]
    assert layer4["resources"] is not None
    assert layer4["resources"]["rules"], "第4层没有返回授权规则"
    assert any(rule["code"] == "AUTH-2026-001" for rule in layer4["resources"]["rules"]), (
        "第4层没有按流程范围返回授权规则"
    )
    assert layer4["resources"]["exceptions"], "第4层没有返回例外台账"

    listed = client.get(f"{API}/pilot/paths").json()
    assert path["id"] in {row["id"] for row in listed}
    client.delete(f"{API}/pilot/paths/{path['id']}")


def test_advance_is_blocked_by_exit_conditions(client):
    path = _create_path(client, name="推进门禁测试")
    pid = path["id"]
    try:
        issue = client.post(
            f"{API}/pilot/paths/{pid}/issues",
            json={"layer_no": 1, "title": "门禁阻断", "severity": "BLOCKER"},
        )
        assert issue.status_code == 201, issue.text
        blocked = client.post(f"{API}/pilot/paths/{pid}/advance")
        assert blocked.status_code == 409
        detail = blocked.json()["detail"]
        assert detail["message"]
        assert any("阻断" in item for item in detail["missing"])

        client.patch(f"{API}/pilot/issues/{issue.json()['id']}", json={"status": "CLOSED"})
        after = client.post(f"{API}/pilot/paths/{pid}/advance")
        if after.status_code == 200:
            assert after.json()["current_layer"] == 2
        else:
            assert "阻断" not in str(after.json()["detail"])
    finally:
        client.delete(f"{API}/pilot/paths/{pid}")


def test_tasks_and_issues_on_layer_four(client):
    path = _create_path(client, name="第4层工作区测试")
    pid = path["id"]
    try:
        task = client.post(
            f"{API}/pilot/paths/{pid}/tasks",
            json={
                "layer_no": 4,
                "title": "补充夜班升级接收人",
                "priority": "HIGH",
                "due_date": "2026-11-05",
                "acceptance": "夜班异常有具体接收人",
            },
        )
        assert task.status_code == 201, task.text
        task = task.json()
        assert task["status"] == "TODO"
        assert task["priority_label"] == "高"

        done = client.patch(f"{API}/pilot/tasks/{task['id']}", json={"status": "DONE"})
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "DONE"
        assert done.json()["completed_at"]

        issue = client.post(
            f"{API}/pilot/paths/{pid}/issues",
            json={
                "layer_no": 4,
                "title": "夜班无升级接收人",
                "severity": "BLOCKER",
                "workaround": "值班负责人代接收",
                "verification": "连续 3 次夜班演练成功",
            },
        )
        assert issue.status_code == 201, issue.text
        issue = issue.json()
        assert issue["severity_label"] == "阻断"

        detail = client.get(f"{API}/pilot/paths/{pid}").json()
        layer4 = next(row for row in detail["layers"] if row["layer_no"] == 4)
        assert layer4["status"] == "BLOCKED"
        assert layer4["gate_open"] is False
        assert layer4["tasks"][0]["title"] == "补充夜班升级接收人"
        assert layer4["issues"][0]["title"] == "夜班无升级接收人"

        closed = client.patch(f"{API}/pilot/issues/{issue['id']}", json={"status": "CLOSED"})
        assert closed.status_code == 200
        assert closed.json()["status"] == "CLOSED"
        assert closed.json()["closed_at"]
        detail = client.get(f"{API}/pilot/paths/{pid}").json()
        layer4 = next(row for row in detail["layers"] if row["layer_no"] == 4)
        assert layer4["status"] != "BLOCKED"
    finally:
        client.delete(f"{API}/pilot/paths/{pid}")


def test_layer_notes_and_path_update(client):
    path = _create_path(client, name="备注测试")
    pid = path["id"]
    try:
        updated = client.patch(
            f"{API}/pilot/paths/{pid}/layers/4",
            json={"context_summary": "目标、边界、职责已确认", "notes": "夜班升级人待补"},
        )
        assert updated.status_code == 200, updated.text
        layer4 = next(row for row in updated.json()["layers"] if row["layer_no"] == 4)
        assert layer4["context_summary"] == "目标、边界、职责已确认"
        assert layer4["notes"] == "夜班升级人待补"

        renamed = client.patch(f"{API}/pilot/paths/{pid}", json={"name": "备注测试（修订）"})
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "备注测试（修订）"
    finally:
        client.delete(f"{API}/pilot/paths/{pid}")


def test_permissions(client, owner_client, viewer_client):
    process = _l3(viewer_client)
    assert (
        viewer_client.post(
            f"{API}/pilot/paths", json={"name": "只读创建", "process_id": process["id"]}
        ).status_code
        == 403
    )

    path = _create_path(client, name="Owner 操作的路径")
    pid = path["id"]
    try:
        task = owner_client.post(
            f"{API}/pilot/paths/{pid}/tasks",
            json={"layer_no": 4, "title": "Owner 可加待办", "priority": "MEDIUM"},
        )
        assert task.status_code == 201, task.text
        assert (
            viewer_client.post(
                f"{API}/pilot/paths/{pid}/tasks",
                json={"layer_no": 4, "title": "只读加待办"},
            ).status_code
            == 403
        )
        assert owner_client.post(f"{API}/pilot/paths/{pid}/advance").status_code == 403
    finally:
        client.delete(f"{API}/pilot/paths/{pid}")
