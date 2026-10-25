"""五阶段项目工作台：步骤闭环、证据门槛与阶段推进。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _project(client) -> dict:
    created = client.post(
        f"{API}/projects",
        json={
            "name": "工作台测试项目 " + uuid.uuid4().hex[:4],
            "methodology": "BPI",
            "owner": "流程管理科",
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_project_detail_exposes_step_status_labels(client):
    """项目详情的步骤下拉必须由后端下发六状态标签，前端不自己维护映射。"""
    project = _project(client)
    try:
        detail = client.get(f"{API}/projects/{project['id']}")
        assert detail.status_code == 200, detail.text
        labels = detail.json()["step_status_labels"]
        assert labels["PENDING_VERIFY"] == "待验证"
        assert labels["BLOCKED"] == "受阻"
        assert labels["DECISION"] == "需决策"
    finally:
        client.delete(f"{API}/projects/{project['id']}")


def test_workbench_seeds_gate_and_blocks_advance(client):
    project = _project(client)
    try:
        wb = client.get(f"{API}/projects/{project['id']}/workflow")
        assert wb.status_code == 200, wb.text
        body = wb.json()
        assert body["project"]["current_stage"] == 1
        assert body["current_stage"]["stage_no"] == 1
        assert body["gate"]["total"] >= 3
        assert body["gate"]["can_advance"] is False
        assert body["steps"]
        assert body["step_status_labels"]["DONE"] == "已满足"

        blocked = client.post(f"{API}/projects/{project['id']}/workflow/advance")
        assert blocked.status_code == 400
        assert "阶段门未通过" in blocked.json()["detail"]

        for condition in body["gate"]["conditions"]:
            updated = client.patch(
                f"{API}/projects/{project['id']}/workflow/conditions/{condition['id']}",
                json={
                    "is_met": True,
                    "evidence": "证据-" + str(condition["id"]),
                    "owner": "流程管理科",
                },
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["gate"]["met_count"] >= 1

        advanced = client.post(f"{API}/projects/{project['id']}/workflow/advance")
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["current_stage"] == 2

        historical = client.get(
            f"{API}/projects/{project['id']}/workflow", params={"stage_no": 1}
        ).json()
        assert historical["read_only"] is True
        assert historical["viewing_stage"] == 1
    finally:
        client.delete(f"{API}/projects/{project['id']}")


def test_step_status_requires_evidence_and_sets_done(client):
    project = _project(client)
    try:
        body = client.get(f"{API}/projects/{project['id']}/workflow").json()
        step = body["steps"][0]
        blocked = client.patch(
            f"{API}/projects/{project['id']}/workflow/steps/{step['id']}",
            json={"status": "BLOCKED"},
        )
        assert blocked.status_code == 400
        assert "受阻状态" in blocked.json()["detail"]

        pending = client.patch(
            f"{API}/projects/{project['id']}/workflow/steps/{step['id']}",
            json={"status": "PENDING_VERIFY"},
        )
        assert pending.status_code == 400
        assert "接收方" in pending.json()["detail"]

        done = client.patch(
            f"{API}/projects/{project['id']}/workflow/steps/{step['id']}",
            json={"status": "DONE", "evidence": ["现场记录 xlsx"], "next_action": "进入下一步"},
        )
        assert done.status_code == 200, done.text
        row = next(item for item in done.json()["steps"] if item["id"] == step["id"])
        assert row["status"] == "DONE"
        assert row["status_label"] == "已满足"
        assert row["verified_by"] == "系统管理员"
    finally:
        client.delete(f"{API}/projects/{project['id']}")
