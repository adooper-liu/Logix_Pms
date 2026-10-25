"""流程模型作为项目交付物来源：只引用版本，不复制文件。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process(client) -> dict:
    code = "L3-MDL-" + uuid.uuid4().hex[:6].upper()
    response = client.post(
        f"{API}/process-map",
        json={"code": code, "name": "模型来源测试流程", "level": 3},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _published_model(client, process_id: int) -> int:
    saved = client.put(
        f"{API}/processes/{process_id}/design",
        json={
            "nodes": [
                {
                    "node_key": "a",
                    "name": "测试活动",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 10,
                }
            ],
            "edges": [],
        },
    )
    assert saved.status_code == 200, saved.text
    published = client.post(f"{API}/processes/{process_id}/design/publish", json={})
    assert published.status_code == 200, published.text
    return published.json()["version_id"]


def _project(client, process_id: int) -> dict:
    response = client.post(
        f"{API}/projects",
        json={
            "name": "模型来源测试项目 " + uuid.uuid4().hex[:4],
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": process_id,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_published_model_becomes_deliverable_version(client):
    process = _process(client)
    project = None
    try:
        version_id = _published_model(client, process["id"])
        project = _project(client, process["id"])

        items = client.get(f"{API}/projects/{project['id']}/deliverables").json()
        as_is = next(row for row in items if row["step_no"] == "2.1")
        assert as_is["current_version"] is None

        linked = client.post(
            f"{API}/deliverables/{as_is['id']}/versions/from-model",
            json={"model_version_id": version_id, "note": "以已发布模型作为证据"},
        )
        assert linked.status_code == 201, linked.text
        detail = linked.json()
        current = detail["current_version"]
        assert current["source_kind"] == "MODEL"
        assert current["source_model_version_id"] == version_id
        assert current["has_model"] is True
        assert current["has_file"] is False
        assert current["status"] == "EFFECTIVE"
        assert "模型 v" in current["source_model_label"]

        summary = client.get(f"{API}/projects/{project['id']}/deliverables/summary").json()
        assert summary["effective"] >= 1
        assert summary["required_missing"] < summary["required_total"]

        # 同一模型版本重复关联是幂等的，不重复生成版本。
        again = client.post(
            f"{API}/deliverables/{as_is['id']}/versions/from-model",
            json={"model_version_id": version_id},
        )
        assert again.status_code == 201, again.text
        assert len(again.json()["versions"]) == 1

        # 1.1 企业流程地图不是流程模型，必须拒绝。
        map_item = next(row for row in items if row["step_no"] == "1.1")
        rejected = client.post(
            f"{API}/deliverables/{map_item['id']}/versions/from-model",
            json={"model_version_id": version_id},
        )
        assert rejected.status_code == 400
        assert "不接受流程模型" in rejected.json()["detail"]
    finally:
        if project is not None:
            client.delete(f"{API}/projects/{project['id']}")
        client.delete(f"{API}/process-map/{process['id']}")


def test_model_from_other_process_is_rejected(client):
    first = _process(client)
    second = _process(client)
    project = None
    try:
        version_id = _published_model(client, first["id"])
        project = _project(client, second["id"])
        items = client.get(f"{API}/projects/{project['id']}/deliverables").json()
        as_is = next(row for row in items if row["step_no"] == "2.1")
        rejected = client.post(
            f"{API}/deliverables/{as_is['id']}/versions/from-model",
            json={"model_version_id": version_id},
        )
        assert rejected.status_code == 400
        assert "不属于项目关联的流程" in rejected.json()["detail"]
    finally:
        if project is not None:
            client.delete(f"{API}/projects/{project['id']}")
        client.delete(f"{API}/process-map/{first['id']}")
        client.delete(f"{API}/process-map/{second['id']}")
