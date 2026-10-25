"""BPMN 元素评论与路径模拟。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process(client) -> int:
    code = "L3-COLLAB-" + uuid.uuid4().hex[:4].upper()
    created = client.post(
        f"{API}/process-map",
        json={"code": code, "name": "协作测试流程", "level": 3},
    )
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _save_design(client, pid: int) -> None:
    saved = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {"node_key": "start", "name": "开始", "node_type": "START", "lane": "L"},
                {
                    "node_key": "gw",
                    "name": "判断",
                    "node_type": "DECISION",
                    "lane": "L",
                    "duration_minutes": 0,
                },
                {
                    "node_key": "fast",
                    "name": "快速路径",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 10,
                    "cost": 1,
                },
                {
                    "node_key": "slow",
                    "name": "慢速路径",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 30,
                    "cost": 3,
                },
                {"node_key": "end", "name": "结束", "node_type": "END", "lane": "L"},
            ],
            "edges": [
                {"source_key": "start", "target_key": "gw"},
                {"source_key": "gw", "target_key": "fast", "probability": 0.7},
                {"source_key": "gw", "target_key": "slow", "probability": 0.3},
                {"source_key": "fast", "target_key": "end"},
                {"source_key": "slow", "target_key": "end"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text


def test_path_simulation(client):
    pid = _process(client)
    try:
        _save_design(client, pid)
        result = client.post(f"{API}/processes/{pid}/design/simulate", json={"max_paths": 10})
        assert result.status_code == 200, result.text
        body = result.json()
        assert body["path_count"] == 2
        assert abs(body["total_probability"] - 1.0) < 1e-6
        assert abs(body["expected_cycle_minutes"] - 16.0) < 0.01
        assert abs(body["expected_cost"] - 1.6) < 0.01
        probs = sorted(row["probability"] for row in body["paths"])
        assert abs(probs[0] - 0.3) < 1e-6 and abs(probs[1] - 0.7) < 1e-6
    finally:
        assert client.delete(f"{API}/process-map/{pid}").status_code == 200


def test_element_comments(client, viewer_client):
    pid = _process(client)
    try:
        created = client.post(
            f"{API}/processes/{pid}/comments",
            json={
                "element_id": "gw",
                "element_name": "判断",
                "element_type": "ExclusiveGateway",
                "body": "这里的默认分支需要补条件",
            },
        )
        assert created.status_code == 201, created.text
        comment = created.json()
        assert comment["status"] == "OPEN"
        assert comment["author_name"] == "系统管理员"

        rows = client.get(f"{API}/processes/{pid}/comments", params={"element_id": "gw"}).json()
        assert any(row["id"] == comment["id"] for row in rows)

        assert (
            viewer_client.post(
                f"{API}/processes/{pid}/comments",
                json={"element_id": "gw", "body": "越权评论"},
            ).status_code
            == 403
        )

        resolved = client.post(f"{API}/processes/{pid}/comments/{comment['id']}/resolve")
        assert resolved.status_code == 200, resolved.text
        assert resolved.json()["status"] == "RESOLVED"
        assert resolved.json()["resolved_by_name"] == "系统管理员"
    finally:
        assert client.delete(f"{API}/process-map/{pid}").status_code == 200
