"""任务实际工时采集与工作量汇总。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == "L3-032")


def _form_data(task: dict) -> dict:
    data = {}
    for field in task.get("form_schema") or []:
        key = field["key"]
        if field.get("type") == "number":
            data[key] = 1
        elif field.get("type") == "select":
            options = field.get("options") or [""]
            data[key] = options[0]
        elif field.get("type") == "checkbox":
            data[key] = True
        else:
            data[key] = "E2E"
    return data


def test_complete_with_effort_and_supplement(client):
    pid = _process_id(client)
    started = client.post(f"{API}/execution/instances", json={"process_id": pid})
    assert started.status_code == 201, started.text
    instance_id = started.json()["id"]
    try:
        detail = client.get(f"{API}/execution/instances/{instance_id}").json()
        task = detail["tasks"][0] if detail["tasks"] else None
        if task is None:
            # 某些种子流程的第一个节点可能已经完成，取当前 open 任务
            tasks = client.get(f"{API}/execution/tasks?instance_id={instance_id}").json()
            task = tasks[0]
        assert task["standard_minutes"] > 0, task

        completed = client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={"form_data": _form_data(task), "effort_minutes": 30},
        )
        assert completed.status_code == 200, completed.text
        body = completed.json()
        assert body["actual_minutes"] == 30
        assert body["standard_minutes"] == task["standard_minutes"]

        worklogs = client.get(f"{API}/execution/tasks/{task['id']}/worklogs").json()
        assert len(worklogs) == 1
        assert worklogs[0]["work_type"] == "HANDLE"
        assert worklogs[0]["effort_minutes"] == 30

        added = client.post(
            f"{API}/execution/tasks/{task['id']}/worklogs",
            json={"work_type": "REWORK", "effort_minutes": 15, "note": "返工补录"},
        )
        assert added.status_code == 201, added.text

        refreshed = client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert refreshed["actual_minutes"] == 45

        summary = client.get(f"{API}/execution/workload").json()
        assert summary["total_minutes"] >= 45
        assert any(row["effort_minutes"] >= 45 for row in summary["rows"])
    finally:
        client.delete(f"{API}/execution/instances/{instance_id}")


def test_worklog_requires_permission(viewer_client, client):
    pid = _process_id(client)
    started = client.post(f"{API}/execution/instances", json={"process_id": pid})
    instance_id = started.json()["id"]
    try:
        detail = client.get(f"{API}/execution/instances/{instance_id}").json()
        task = detail["tasks"][0]
        denied = viewer_client.post(
            f"{API}/execution/tasks/{task['id']}/worklogs",
            json={"effort_minutes": 10},
        )
        assert denied.status_code == 403
    finally:
        client.delete(f"{API}/execution/instances/{instance_id}")
