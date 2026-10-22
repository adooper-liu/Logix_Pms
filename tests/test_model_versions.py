"""流程模型版本：草稿、评审、发布、差异与回滚。"""

from __future__ import annotations

API = "/api/v1"


def _create_process(client, code: str = "L3-MVER") -> int:
    response = client.post(
        f"{API}/process-map",
        json={"code": code, "name": "模型版本测试", "level": 3},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _model(nodes: list[dict], edges: list[dict] | None = None) -> dict:
    return {"nodes": nodes, "edges": edges or []}


def _node(key: str, name: str = "活动") -> dict:
    return {
        "node_key": key,
        "name": name,
        "node_type": "TASK",
        "lane": "L",
        "duration_minutes": 10,
    }


def _versions(client, pid: int) -> list[dict]:
    response = client.get(f"{API}/processes/{pid}/design/versions")
    assert response.status_code == 200, response.text
    return response.json()


def test_update_node_metrics_in_draft(client):
    pid = _create_process(client, "L3-MNODE")
    try:
        saved = client.put(
            f"{API}/processes/{pid}/design",
            json=_model([_node("a")]),
        )
        assert saved.status_code == 200, saved.text

        patched = client.patch(
            f"{API}/processes/{pid}/design/nodes/a",
            json={
                "duration_minutes": 25,
                "wait_minutes": 5,
                "cost": 7.5,
                "rework_rate": 0.2,
                "approval_levels": 2,
                "is_value_added": False,
                "expected_version": 1,
            },
        )
        assert patched.status_code == 200, patched.text
        node = patched.json()["nodes"][0]
        assert node["duration_minutes"] == 25
        assert node["wait_minutes"] == 5
        assert node["cost"] == 7.5
        assert node["rework_rate"] == 0.2
        assert node["approval_levels"] == 2
        assert node["is_value_added"] is False

        analysis = client.post(f"{API}/processes/{pid}/design/analyze").json()
        assert analysis["metrics"]["lead_time_minutes"] == 37.5

        missing = client.patch(
            f"{API}/processes/{pid}/design/nodes/ghost",
            json={"duration_minutes": 1},
        )
        assert missing.status_code == 404
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_draft_review_publish_diff_and_rollback(client, manager_client, owner_client):
    pid = _create_process(client)
    try:
        draft = client.put(
            f"{API}/processes/{pid}/design",
            json=_model([_node("a"), _node("b")], [{"source_key": "a", "target_key": "b"}]),
        )
        assert draft.status_code == 200, draft.text
        assert draft.json()["status"] == "DRAFT"
        assert draft.json()["version"] == 1
        v1_id = draft.json()["version_id"]

        # 草稿节点也可以先配执行分派/时限，发布后生效
        assignment = client.put(
            f"{API}/execution/assignments",
            json={"process_id": pid, "node_key": "a", "due_hours": 2},
        )
        assert assignment.status_code == 200, assignment.text
        assert assignment.json()["due_hours"] == 2

        published = manager_client.post(
            f"{API}/processes/{pid}/design/publish",
            json={"expected_version": 1, "change_note": "首次发布"},
        )
        assert published.status_code == 200, published.text
        assert published.json()["status"] == "PUBLISHED"
        assert published.json()["published_version"] == 1

        executable = manager_client.get(f"{API}/execution/processes").json()
        row = next(item for item in executable if item["code"] == "L3-MVER")
        assert row["node_count"] == 2
        assert row["model_version"] == 1

        # 草稿修改不影响已发布运行时
        draft2 = client.put(
            f"{API}/processes/{pid}/design",
            json=_model(
                [_node("a", "活动 A 改"), _node("b"), _node("c")],
                [
                    {"source_key": "a", "target_key": "b"},
                    {"source_key": "b", "target_key": "c"},
                ],
            ),
        )
        assert draft2.status_code == 200, draft2.text
        assert draft2.json()["status"] == "DRAFT"
        assert draft2.json()["version"] == 2
        v2_id = draft2.json()["version_id"]
        still = manager_client.get(f"{API}/execution/processes").json()
        assert next(item for item in still if item["code"] == "L3-MVER")["node_count"] == 2

        versions = _versions(client, pid)
        assert [v["version"] for v in versions] == [2, 1]
        diff = client.get(
            f"{API}/processes/{pid}/design/diff",
            params={"from_version_id": v1_id, "to_version_id": v2_id},
        ).json()
        assert [item["node_key"] for item in diff["nodes_added"]] == ["c"]
        assert diff["nodes_changed"][0]["node_key"] == "a"
        assert diff["edges_added"][0]["source_key"] == "b"

        submitted = client.post(
            f"{API}/processes/{pid}/design/submit-review", json={"note": "请评审"}
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "IN_REVIEW"
        blocked = client.put(
            f"{API}/processes/{pid}/design",
            json=_model([_node("a")]),
        )
        assert blocked.status_code == 409

        rejected = manager_client.post(
            f"{API}/processes/{pid}/design/reject", json={"note": "补充说明"}
        )
        assert rejected.status_code == 200, rejected.text
        assert rejected.json()["status"] == "DRAFT"

        # 评审后重新提交并发布 v2，运行时节点数变为 3
        client.post(f"{API}/processes/{pid}/design/submit-review", json={})
        published2 = manager_client.post(
            f"{API}/processes/{pid}/design/publish", json={"expected_version": 2}
        )
        assert published2.status_code == 200, published2.text
        assert published2.json()["published_version"] == 2
        live2 = manager_client.get(f"{API}/execution/processes").json()
        assert next(item for item in live2 if item["code"] == "L3-MVER")["node_count"] == 3

        # 回滚 v1 会生成新草稿，发布后才影响运行时
        rolled = client.post(
            f"{API}/processes/{pid}/design/versions/{v1_id}/rollback",
            json={"note": "回到 v1"},
        )
        assert rolled.status_code == 200, rolled.text
        assert rolled.json()["status"] == "DRAFT"
        assert len(rolled.json()["nodes"]) == 2
        live_after_rollback = manager_client.get(f"{API}/execution/processes").json()
        assert (
            next(item for item in live_after_rollback if item["code"] == "L3-MVER")["node_count"]
            == 3
        )

        published3 = manager_client.post(
            f"{API}/processes/{pid}/design/publish", json={"expected_version": 3}
        )
        assert published3.status_code == 200, published3.text
        live3 = manager_client.get(f"{API}/execution/processes").json()
        assert next(item for item in live3 if item["code"] == "L3-MVER")["node_count"] == 2

        # 只有 MANAGER+ 能发布
        assert (
            owner_client.post(
                f"{API}/processes/{pid}/design/publish", json={"expected_version": 4}
            ).status_code
            == 403
        )
    finally:
        client.delete(f"{API}/process-map/{pid}")
