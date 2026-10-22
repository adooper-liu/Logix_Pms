"""设计器模型校验：自环、重复连线、草稿警告与保存拦截。"""

from __future__ import annotations

API = "/api/v1"


def _node(key: str, node_type: str = "TASK") -> dict:
    return {"node_key": key, "name": key.upper(), "node_type": node_type, "lane": "L"}


def test_inline_validation_reports_errors_and_warnings(client):
    response = client.post(
        f"{API}/design/validate",
        json={
            "nodes": [_node("a"), _node("b")],
            "edges": [
                {"source_key": "a", "target_key": "a"},
                {"source_key": "a", "target_key": "b"},
                {"source_key": "a", "target_key": "b"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert any("自环" in item for item in body["errors"])
    assert any("重复连线" in item for item in body["errors"])
    assert any("没有开始节点" in item for item in body["warnings"])
    assert any("没有结束节点" in item for item in body["warnings"])


def test_saved_design_rejects_hard_errors(client):
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-VALID", "name": "校验测试流程", "level": 3},
    ).json()
    pid = created["id"]
    try:
        response = client.put(
            f"{API}/processes/{pid}/design",
            json={
                "nodes": [_node("a")],
                "edges": [{"source_key": "a", "target_key": "a"}],
            },
        )
        assert response.status_code == 400, response.text
        assert "自环" in response.json()["detail"]

        # 未完成的草稿（没有开始/结束）只产生警告，允许保存
        draft = client.put(
            f"{API}/processes/{pid}/design",
            json={"nodes": [_node("a")], "edges": []},
        )
        assert draft.status_code == 200, draft.text

        checked = client.post(f"{API}/processes/{pid}/design/validate")
        assert checked.status_code == 200
        assert checked.json()["errors"] == []
        assert checked.json()["warnings"]
    finally:
        client.delete(f"{API}/process-map/{pid}")
