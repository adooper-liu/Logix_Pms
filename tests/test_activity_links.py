"""统一活动 ID、活动级制度/工具绑定、组织归属。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _node(client, process_id: int, key: str) -> dict:
    model = client.get(f"{API}/processes/{process_id}/design").json()
    return next(item for item in model["nodes"] if item["node_key"] == key)


def test_activity_and_position_links_survive_bpmn_save(client):
    pid = _process_id(client)
    activities = client.get(f"{API}/process-map/flat").json()
    activity = next(item for item in activities if item["code"] == "L4-205")
    position = next(
        item for item in client.get(f"{API}/positions").json() if item["name"] == "采购计划员"
    )

    patched = client.patch(
        f"{API}/processes/{pid}/design/nodes/n6",
        json={"process_arch_id": activity["id"], "owner_position_id": position["id"]},
    )
    assert patched.status_code == 200, patched.text
    node = next(item for item in patched.json()["nodes"] if item["node_key"] == "n6")
    assert node["process_arch_id"] == activity["id"]
    assert node["owner_position_id"] == position["id"]

    xml = client.get(f"{API}/processes/{pid}/bpmn").text
    saved = client.post(
        f"{API}/processes/{pid}/bpmn",
        json={"xml": xml, "expected_version": patched.json()["version"]},
    )
    assert saved.status_code == 200, saved.text
    node = next(item for item in saved.json()["nodes"] if item["node_key"] == "n6")
    assert node["process_arch_id"] == activity["id"], "BPMN 保存后活动 ID 丢失"
    assert node["owner_position_id"] == position["id"], "BPMN 保存后负责人岗位丢失"

    # 还原成 seed 里的正确活动，避免影响其他用例
    original = next(item for item in activities if item["code"] == "L4-206")
    restored = client.patch(
        f"{API}/processes/{pid}/design/nodes/n6",
        json={"process_arch_id": original["id"]},
    )
    assert restored.status_code == 200


def test_activity_must_belong_to_same_process(client):
    pid = _process_id(client, "L3-032")
    other = _process_id(client, "L3-033")
    other_activity = next(
        row
        for row in client.get(f"{API}/process-map/flat").json()
        if row["level"] == 4 and row["parent_id"] == other
    )
    response = client.patch(
        f"{API}/processes/{pid}/design/nodes/n2",
        json={"process_arch_id": other_activity["id"]},
    )
    assert response.status_code == 400
    assert "L4" in response.json()["detail"]


def test_validation_warns_unlinked_activity(client):
    response = client.post(
        f"{API}/design/validate",
        json={
            "nodes": [{"node_key": "a", "name": "未关联活动", "node_type": "TASK", "lane": "L"}],
            "edges": [],
        },
    )
    assert response.status_code == 200
    assert any("未关联 L4 活动" in item for item in response.json()["warnings"])


def test_document_activity_binding(client):
    pid = _process_id(client)
    created = client.post(
        f"{API}/process-documents",
        json={
            "process_id": pid,
            "title": "E2E 活动标准文件",
            "category": "SOP",
            "node_key": "n2",
        },
    )
    assert created.status_code == 201, created.text
    document = created.json()
    assert document["node_key"] == "n2"
    try:
        rows = client.get(f"{API}/process-documents?process_id={pid}&node_key=n2").json()
        assert any(item["id"] == document["id"] for item in rows)
        bad = client.post(
            f"{API}/process-documents",
            json={
                "process_id": pid,
                "title": "错误活动",
                "category": "SOP",
                "node_key": "nope",
            },
        )
        assert bad.status_code == 400
    finally:
        client.delete(f"{API}/process-documents/{document['id']}")


def test_node_tool_binding_crud(client):
    pid = _process_id(client)
    tool = client.get(f"{API}/tools").json()[0]
    base = f"{API}/processes/{pid}/design/nodes/n2/tools"
    created = client.post(
        base,
        json={"tool_code": tool["code"], "level": "RECOMMENDED", "note": "E2E"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["tool_name"] == tool["name"]
    try:
        rows = client.get(base).json()
        assert any(item["tool_code"] == tool["code"] for item in rows)
        duplicate = client.post(base, json={"tool_code": tool["code"]})
        assert duplicate.status_code == 409
    finally:
        deleted = client.delete(f"{base}/{tool['code']}")
        assert deleted.status_code == 200
    assert client.get(base).json() == []
