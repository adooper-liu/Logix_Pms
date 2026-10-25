"""执行层 P2：取消补偿、部署回滚与实例归档。"""

from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models.execution import ProcessInstance

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _minimal_process(client) -> int:
    code = "L3-P2-" + uuid.uuid4().hex[:4].upper()
    created = client.post(
        f"{API}/process-map", json={"code": code, "name": "执行层 P2 测试", "level": 3}
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    saved = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {"node_key": "start", "name": "开始", "node_type": "START", "lane": "L"},
                {
                    "node_key": "task",
                    "name": "处理",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 10,
                },
                {"node_key": "end", "name": "结束", "node_type": "END", "lane": "L"},
            ],
            "edges": [
                {"source_key": "start", "target_key": "task"},
                {"source_key": "task", "target_key": "end"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"expected_version": saved.json()["version"], "change_note": "P2 test"},
    )
    assert published.status_code == 200, published.text
    return pid


def _linear_process(client) -> int:
    code = "L3-P2C-" + uuid.uuid4().hex[:4].upper()
    created = client.post(
        f"{API}/process-map", json={"code": code, "name": "补偿测试流程", "level": 3}
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    saved = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {"node_key": "start", "name": "开始", "node_type": "START", "lane": "L"},
                {"node_key": "a", "name": "步骤A", "node_type": "TASK", "lane": "L"},
                {"node_key": "b", "name": "步骤B", "node_type": "TASK", "lane": "L"},
                {"node_key": "end", "name": "结束", "node_type": "END", "lane": "L"},
            ],
            "edges": [
                {"source_key": "start", "target_key": "a"},
                {"source_key": "a", "target_key": "b"},
                {"source_key": "b", "target_key": "end"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    published = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"expected_version": saved.json()["version"], "change_note": "补偿测试"},
    )
    assert published.status_code == 200, published.text
    return pid


def test_cancel_creates_and_completes_compensation(client):
    pid = _linear_process(client)
    started = client.post(
        f"{API}/execution/instances", json={"process_id": pid, "variables": {"case": "p2"}}
    )
    assert started.status_code == 201, started.text
    iid = started.json()["id"]
    try:
        task = client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        completed = client.post(f"{API}/execution/tasks/{task['id']}/complete", json={})
        assert completed.status_code == 200, completed.text

        action = client.post(
            f"{API}/processes/{pid}/compensations",
            json={
                "node_key": task["node_key"],
                "name": "回滚业财凭证",
                "description": "通知财务冲销已生成凭证",
            },
        )
        assert action.status_code == 200, action.text

        cancelled = client.post(f"{API}/execution/instances/{iid}/cancel")
        assert cancelled.status_code == 200, cancelled.text
        rows = client.get(f"{API}/execution/instances/{iid}/compensations").json()
        record = next(row for row in rows if row["node_key"] == task["node_key"])
        assert record["status"] == "PENDING"
        assert record["action_name"] == "回滚业财凭证"

        completed = client.post(f"{API}/execution/compensations/{record['id']}/complete", json={})
        assert completed.status_code == 200, completed.text
        assert completed.json()["status"] == "DONE"
        assert completed.json()["completed_by"] == "系统管理员"
    finally:
        client.delete(f"{API}/execution/instances/{iid}")
        client.delete(f"{API}/process-map/{pid}")


def test_publish_rollback_to_history(client):
    pid = _minimal_process(client)
    try:
        versions = client.get(f"{API}/processes/{pid}/design/versions").json()
        first_published = next(row for row in versions if row["status"] == "PUBLISHED")
        saved = client.put(
            f"{API}/processes/{pid}/design",
            json={
                "nodes": [
                    {"node_key": "start", "name": "开始2", "node_type": "START", "lane": "L"},
                    {
                        "node_key": "task",
                        "name": "处理2",
                        "node_type": "TASK",
                        "lane": "L",
                    },
                    {"node_key": "end", "name": "结束2", "node_type": "END", "lane": "L"},
                ],
                "edges": [
                    {"source_key": "start", "target_key": "task"},
                    {"source_key": "task", "target_key": "end"},
                ],
            },
        )
        assert saved.status_code == 200, saved.text
        assert (
            client.post(
                f"{API}/processes/{pid}/design/publish",
                json={"expected_version": saved.json()["version"]},
            ).status_code
            == 200
        )

        rolled = client.post(
            f"{API}/processes/{pid}/design/versions/{first_published['id']}/publish-rollback",
            json={"note": "回滚测试"},
        )
        assert rolled.status_code == 200, rolled.text
        names = {node["name"] for node in rolled.json()["nodes"]}
        assert "开始" in names and "开始2" not in names
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_archive_completed_instances(client):
    pid = _minimal_process(client)
    iid = None
    try:
        started = client.post(f"{API}/execution/instances", json={"process_id": pid})
        assert started.status_code == 201, started.text
        iid = started.json()["id"]
        task = client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        assert (
            client.post(f"{API}/execution/tasks/{task['id']}/complete", json={}).status_code == 200
        )

        db = SessionLocal()
        try:
            row = db.get(ProcessInstance, iid)
            row.completed_at = utcnow().replace(year=2020)
            db.commit()
        finally:
            db.close()

        archived = client.post(
            f"{API}/execution/instances/archive", params={"older_than_days": 365}
        )
        assert archived.status_code == 200, archived.text
        ids = [row["id"] for row in client.get(f"{API}/execution/instances").json()]
        assert iid not in ids
        all_ids = [
            row["id"]
            for row in client.get(
                f"{API}/execution/instances", params={"include_archived": True}
            ).json()
        ]
        assert iid in all_ids
    finally:
        if iid is not None:
            client.delete(f"{API}/execution/instances/{iid}")
        client.delete(f"{API}/process-map/{pid}")
