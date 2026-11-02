"""十层单页：路径、层状态、待办与异常闭环。"""

from __future__ import annotations

API = "/api/v1"


def _l3(client) -> dict:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == "L3-032")


def _create_path(client, **overrides) -> dict:
    payload = {"process_id": _l3(client)["id"]}
    payload.update(overrides)
    created = client.post(f"{API}/pilot/paths", json=payload)
    assert created.status_code == 201, created.text
    return created.json()


def test_create_path_uses_process_name(client):
    process = _l3(client)
    path = _create_path(client)
    assert path["name"] == process["name"]
    assert path["process_id"] == process["id"]
    again = client.post(f"{API}/pilot/paths", json={"process_id": process["id"]})
    assert again.status_code == 400, again.text
    assert "已有十层路径" in again.json()["detail"]
    client.delete(f"{API}/pilot/paths/{path['id']}")


def test_create_path_has_ten_layers(client):
    path = _create_path(client)
    closed = [layer for layer in path["layers"] if not layer["gate_open"]]
    if closed:
        assert path["current_layer"] == closed[0]["layer_no"]
    else:
        assert path["current_layer"] == 10
    assert sum(1 for layer in path["layers"] if layer["current"]) == 1
    assert path["status"] == "ACTIVE"
    assert len(path["layers"]) == 10
    assert [layer["layer_no"] for layer in path["layers"]] == list(range(1, 11))
    assert path["layers"][0]["title"] == "战略与目标"
    assert path["layers"][3]["title"] == "制度与授权设计"
    assert 0 <= path["progress"] <= 100
    # 退出门按本流程计数，标签应是本流程口径
    process = _l3(client)
    sample = path["layers"][0]["evidence_items"][0]
    assert "本流程" in sample["label"] or sample["key"] in {"l1", "l2", "l3"}
    published = next(
        item for item in path["layers"][4]["evidence_items"] if item["key"] == "l3_published"
    )
    assert published["view"] == "designer"
    assert published["view_params"]["process"] == str(process["id"])
    assert published["view_params"]["tab"] == "model"
    designer = next(
        action for action in path["layers"][4]["actions"] if action["view"] == "designer"
    )
    assert designer["view_params"]["process"] == str(process["id"])
    for layer in path["layers"]:
        for item in layer["evidence_items"]:
            assert item["view"], f"{layer['title']} · {item['key']} 缺少证据落点"
            assert "view_params" in item
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
            body = after.json()
            assert body["status"] == "COMPLETED"
            assert all(layer["gate_open"] for layer in body["layers"])
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
        viewer_client.post(f"{API}/pilot/paths", json={"process_id": process["id"]}).status_code
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


def test_layers_count_one_kpi_mining_rpa_and_training(client, viewer_client):
    """第 8 层只数同一张 KPI；挖掘、机器人和培训到场各自有计数。"""
    process = _l3(client)
    created = client.post(f"{API}/pilot/paths", json={"process_id": process["id"]})
    if created.status_code == 201:
        detail = created.json()
        owns_path = True
    else:
        listed = client.get(f"{API}/pilot/paths").json()
        path_id = next(row["id"] for row in listed if row["process_id"] == process["id"])
        detail = client.get(f"{API}/pilot/paths/{path_id}").json()
        owns_path = False
    try:
        layer6 = next(layer for layer in detail["layers"] if layer["layer_no"] == 6)
        layer8 = next(layer for layer in detail["layers"] if layer["layer_no"] == 8)
        layer10 = next(layer for layer in detail["layers"] if layer["layer_no"] == 10)
        layer1 = next(layer for layer in detail["layers"] if layer["layer_no"] == 1)
        assert [item["key"] for item in layer1["evidence_items"]] == ["objective_complete"]
        assert "同一条" in layer1["evidence_items"][0]["label"]
        assert [item["key"] for item in layer6["evidence_items"]] == [
            "forms",
            "bindings",
            "mining_variants",
            "rpa_bots",
            "rpa_runs",
            "process_cases",
            "technology_uses",
        ]
        assert [item["key"] for item in layer8["evidence_items"]] == ["kpi_monitored"]
        assert "本流程" in layer8["evidence_items"][0]["label"]
        assert "training_records" in [item["key"] for item in layer10["evidence_items"]]
        users = client.get(f"{API}/start/charter-options").json()["users"]
        owner_id = users[0]["id"]
        rpa = {
            "process_id": process["id"],
            "activity_name": "核对入库单",
            "bot_name": "入库核对机器人",
            "manual_step": "打开系统逐项核对字段",
            "owner_user_id": owner_id,
        }
        assert viewer_client.post(f"{API}/pilot/rpa", json=rpa).status_code == 403
        assert client.post(f"{API}/pilot/rpa", json={**rpa, "manual_step": " "}).status_code == 400
        saved = client.post(f"{API}/pilot/rpa", json=rpa)
        assert saved.status_code == 200, saved.text
        training = {
            "process_id": process["id"],
            "trainee_user_id": owner_id,
            "topic": "这条流程的起止",
            "completed_on": "2026-11-01",
        }
        assert viewer_client.post(f"{API}/pilot/training", json=training).status_code == 403
        trained = client.post(f"{API}/pilot/training", json=training)
        assert trained.status_code == 200, trained.text
        refreshed = client.get(f"{API}/pilot/paths/{detail['id']}").json()
        by_key = {
            item["key"]: item
            for layer in refreshed["layers"]
            if layer["layer_no"] in (6, 10)
            for item in layer["evidence_items"]
        }
        assert by_key["rpa_bots"]["value"] >= 1
        assert by_key["rpa_bots"]["met"] is True
        assert by_key["training_records"]["value"] >= 1
        assert by_key["training_records"]["met"] is True
        assert "mining_variants" in by_key
        event = client.post(
            f"{API}/pilot/event-logs",
            json={
                "process_id": process["id"],
                "source_name": "ERP",
                "case_key": "PO-1",
                "activity_name": "创建采购订单",
                "occurred_at": "2026-11-01T08:00:00",
            },
        )
        assert event.status_code == 200, event.text
        mined = client.get(
            f"{API}/execution/mining",
            params={"process_id": process["id"], "limit": 10},
        )
        assert mined.status_code == 200, mined.text
        assert mined.json()["variant_count"] >= 1
        endpoints = client.get(f"{API}/integrations/endpoints")
        assert endpoints.status_code == 200, endpoints.text
        endpoint_id = endpoints.json()[0]["id"]
        run = client.post(
            f"{API}/pilot/rpa-runs",
            json={
                "bot_id": saved.json()["id"],
                "ran_at": "2026-11-01T09:00:00",
                "outcome": "SUCCEEDED",
                "endpoint_id": endpoint_id,
            },
        )
        assert run.status_code == 200, run.text
        case = client.post(
            f"{API}/pilot/cases",
            json={
                "process_id": process["id"],
                "title": "资质临时例外",
                "situation": "供应商证照过期一天，不能按固定步骤放行",
                "owner_user_id": owner_id,
            },
        )
        assert case.status_code == 200, case.text
        kinds = client.get(f"{API}/pilot/technology-kinds")
        assert kinds.status_code == 200, kinds.text
        assert {row["code"] for row in kinds.json()} == {"BLOCKCHAIN", "AI", "IOT"}
        tech = client.post(
            f"{API}/pilot/technology-uses",
            json={
                "process_id": process["id"],
                "kind": "AI",
                "name": "入库照片识别",
                "usage_note": "收货拍照后识别单号，人仍要确认",
                "owner_user_id": owner_id,
            },
        )
        assert tech.status_code == 200, tech.text
        again = client.get(f"{API}/pilot/paths/{detail['id']}").json()
        again_keys = {
            item["key"]: item
            for layer in again["layers"]
            if layer["layer_no"] == 6
            for item in layer["evidence_items"]
        }
        assert again_keys["mining_variants"]["value"] >= 1
        assert again_keys["rpa_runs"]["value"] >= 1
        assert again_keys["process_cases"]["value"] >= 1
        assert again_keys["technology_uses"]["value"] >= 1
    finally:
        if owns_path:
            client.delete(f"{API}/pilot/paths/{detail['id']}")
