"""L5 任务目录与标准工时绑定。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _l4(client) -> dict:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["level"] == 4)


def test_l5_task_catalog_and_rollup(client):
    activity = _l4(client)
    code = "T-" + uuid.uuid4().hex[:6].upper()
    created = client.post(
        f"{API}/process-tasks",
        json={
            "activity_id": activity["id"],
            "code": code,
            "name": "汇总采购需求",
            "standard_minutes": 35,
            "frequency": "2 次/周",
        },
    )
    assert created.status_code == 201, created.text
    task = created.json()
    assert task["activity_id"] == activity["id"]
    assert task["standard_minutes"] == 35

    rows = client.get(f"{API}/process-tasks", params={"activity_id": activity["id"]}).json()
    assert any(row["id"] == task["id"] for row in rows)

    rollup = client.get(
        f"{API}/process-tasks/rollup", params={"activity_id": activity["id"]}
    ).json()
    assert any(row["id"] == task["id"] for row in rollup["tasks"])
    assert rollup["total_standard_minutes"] >= 35

    updated = client.patch(f"{API}/process-tasks/{task['id']}", json={"standard_minutes": 42})
    assert updated.status_code == 200, updated.text
    assert updated.json()["standard_minutes"] == 42
    assert client.delete(f"{API}/process-tasks/{task['id']}").status_code == 200


def test_standard_hours_can_bind_l5_task(client):
    activity = _l4(client)
    positions = client.get(f"{API}/positions").json()
    assert positions
    code = "T-" + uuid.uuid4().hex[:6].upper()
    task = client.post(
        f"{API}/process-tasks",
        json={
            "activity_id": activity["id"],
            "code": code,
            "name": "标准工时绑定任务",
            "standard_minutes": 20,
        },
    ).json()

    created = client.post(
        f"{API}/workload/standards",
        json={
            "name": "任务级标准工时",
            "activity_id": activity["id"],
            "task_id": task["id"],
            "position_id": positions[0]["id"],
            "method_description": "任务级观测",
            "source": "TIME_STUDY",
            "observed_minutes": 18,
            "rating_factor": 1.1,
            "allowance_rate": 0.1,
            "sample_size": 5,
            "monthly_frequency": 8,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["task_id"] == task["id"]
    assert body["task_code"] == code
    assert body["activity_id"] == activity["id"]

    # 清理：停用标准与任务，避免影响其它用例的精确计数
    assert client.post(f"{API}/workload/standards/{body['id']}/retire").status_code == 200
    assert client.delete(f"{API}/process-tasks/{task['id']}").status_code == 200

    # 任务必须属于所选活动
    other = next(
        row
        for row in client.get(f"{API}/process-map/flat").json()
        if row["level"] == 4 and row["id"] != activity["id"]
    )
    rejected = client.post(
        f"{API}/workload/standards",
        json={
            "name": "跨活动任务绑定",
            "activity_id": other["id"],
            "task_id": task["id"],
            "position_id": positions[0]["id"],
            "method_description": "非法绑定",
            "source": "TIME_STUDY",
            "observed_minutes": 10,
            "sample_size": 1,
        },
    )
    assert rejected.status_code == 400
    assert "必须属于所选 L4 活动" in rejected.json()["detail"]
