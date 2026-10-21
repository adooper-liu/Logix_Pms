"""表单定义与分支规则：校验、快照、规则命中。"""

from __future__ import annotations

from app.services import forms as forms_service

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(r["id"] for r in rows if r["code"] == code)


def _start(client) -> dict:
    r = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client), "variables": {"case": "form-test"}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _open_task(client, instance_id: int) -> dict:
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    assert tasks
    return tasks[0]


def _complete(client, task_id: int, **payload):
    return client.post(f"{API}/execution/tasks/{task_id}/complete", json=payload)


def test_forms_and_rules_are_seeded(client):
    pid = _process_id(client)
    forms = client.get(f"{API}/execution/forms", params={"process_id": pid}).json()
    by_node = {f["node_key"]: f for f in forms}
    assert {"n1", "n4"} <= set(by_node)
    assert any(f["key"] == "applicant" for f in by_node["n1"]["fields"])
    assert any(f["key"] == "approved" for f in by_node["n4"]["fields"])

    rules = client.get(f"{API}/execution/rules", params={"process_id": pid}).json()
    assert any(r["node_key"] == "n4" and r["target_node_key"] == "n5" for r in rules)


def test_form_validation_and_task_schema(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        assert task["form_name"] == "需求发起"
        assert {f["key"] for f in task["form_schema"]} == {"applicant", "amount", "description"}

        missing = _complete(client, task["id"], form_data={})
        assert missing.status_code == 400
        assert "申请人为必填" in missing.json()["detail"]

        bad_number = _complete(client, task["id"], form_data={"applicant": "测试", "amount": "abc"})
        assert bad_number.status_code == 400
        assert "必须是数字" in bad_number.json()["detail"]

        ok = _complete(
            client,
            task["id"],
            form_data={"applicant": "测试", "amount": 12000, "description": "采购"},
        )
        assert ok.status_code == 200, ok.text
        assert ok.json()["form_data"]["amount"] == 12000.0
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


def test_form_snapshot_is_frozen_at_start(client):
    pid = _process_id(client)
    form = client.get(
        f"{API}/execution/forms", params={"process_id": pid, "node_key": "n1"}
    ).json()[0]
    original = form["fields"]

    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        assert len(task["form_schema"]) == 3

        # 修改表单定义不应影响已启动实例的快照
        changed = client.patch(f"{API}/execution/forms/{form['id']}", json={"fields": []})
        assert changed.status_code == 200, changed.text
        again = client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert len(again["form_schema"]) == 3, "运行中实例应使用启动时的表单快照"
    finally:
        client.patch(f"{API}/execution/forms/{form['id']}", json={"fields": original})
        client.delete(f"{API}/execution/instances/{iid}")


def test_duplicate_form_rejected(client):
    pid = _process_id(client)
    form = client.get(
        f"{API}/execution/forms", params={"process_id": pid, "node_key": "n1"}
    ).json()[0]
    duplicate = client.post(
        f"{API}/execution/forms",
        json={"process_id": pid, "node_key": "n1", "name": "重复", "fields": []},
    )
    assert duplicate.status_code == 409
    assert form["id"]


def test_rule_target_must_be_outgoing(manager_client):
    pid = _process_id(manager_client)
    bad = manager_client.post(
        f"{API}/execution/rules",
        json={
            "process_id": pid,
            "node_key": "n4",
            "name": "非法目标",
            "conditions": [{"field": "approved", "op": "eq", "value": "否"}],
            "target_node_key": "n1",
        },
    )
    assert bad.status_code == 400
    assert "不是节点" in bad.json()["detail"]


def test_rule_engine_controls_branch(manager_client):
    """新增「审批不通过 → n6」规则后，审批否应自动进入回退节点。"""
    pid = _process_id(manager_client)
    rule = manager_client.post(
        f"{API}/execution/rules",
        json={
            "process_id": pid,
            "node_key": "n4",
            "name": "审批不通过 → 回退修改",
            "conditions": [{"field": "approved", "op": "eq", "value": "否"}],
            "target_node_key": "n6",
            "priority": 20,
        },
    )
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["id"]

    instance = _start(manager_client)
    iid = instance["id"]
    try:
        for step in range(3):
            task = _open_task(manager_client, iid)
            data = {"applicant": "规则测试", "amount": 3000} if step == 0 else None
            assert _complete(manager_client, task["id"], form_data=data).status_code == 200

        n4 = _open_task(manager_client, iid)
        assert n4["node_key"] == "n4"
        # 没有显式 next_node_key，规则应自动选择 n6
        assert _complete(manager_client, n4["id"], form_data={"approved": "否"}).status_code == 200
        n6 = _open_task(manager_client, iid)
        assert n6["node_key"] == "n6"
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")
        manager_client.delete(f"{API}/execution/rules/{rule_id}")


def test_rule_condition_evaluator():
    rules = [
        {
            "conditions": [{"field": "amount", "op": "gte", "value": 10000}],
            "target": "HIGH",
        },
        {"conditions": [], "target": "DEFAULT"},
    ]
    assert forms_service.evaluate_rules(rules, {"amount": 15000}) == "HIGH"
    assert forms_service.evaluate_rules(rules, {"amount": 5000}) == "DEFAULT"

    assert forms_service._match({"field": "a", "op": "in", "value": [1, 2]}, {"a": 2})
    assert forms_service._match({"field": "a", "op": "contains", "value": "x"}, {"a": ["x", "y"]})
    assert forms_service._match({"field": "a", "op": "truthy"}, {"a": True})
    assert forms_service._match({"field": "a", "op": "falsy"}, {"a": ""})
    assert not forms_service._match({"field": "a", "op": "gt", "value": 5}, {"a": "x"})
