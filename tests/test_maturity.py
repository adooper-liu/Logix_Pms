"""成熟度评估与阶段门禁：证据、覆盖度与阶段推进拦截。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)["id"]


def _create_project(client) -> dict:
    created = client.post(
        f"{API}/projects",
        json={
            "name": "门禁测试项目",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": _process_id(client),
        },
    )
    assert created.status_code == 201, created.text
    return created.json()


def test_maturity_assessment_and_coverage(client):
    meta = client.get(f"{API}/maturity/meta").json()
    assert meta["dimension_labels"]["GOVERNANCE"] == "治理与责任"
    assert meta["conclusion_labels"]["PASS"] == "通过"

    process_id = _process_id(client)
    created = client.post(
        f"{API}/maturity/assessments",
        json={
            "process_id": process_id,
            "dimension": "GOVERNANCE",
            "level": 3,
            "evidence_url": "https://example.com/maturity-report.pdf",
            "note": "治理角色与 RACI 已覆盖",
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["level"] == 3
    assert body["dimension_label"] == "治理与责任"
    assert body["assessed_by"] == "系统管理员"

    rows = client.get(f"{API}/maturity/assessments", params={"process_id": process_id}).json()
    assert any(row["id"] == body["id"] for row in rows)

    coverage = client.get(f"{API}/maturity/coverage")
    assert coverage.status_code == 200, coverage.text
    summary = coverage.json()
    assert "rows" in summary
    assert summary["l4_total"] >= 0


def test_gate_blocks_stage_advance_until_pass(client):
    project = _create_project(client)
    project_id = project["id"]
    try:
        enabled = client.patch(f"{API}/projects/{project_id}", json={"gate_required": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["gate_required"] is True

        blocked = client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2})
        assert blocked.status_code == 400, blocked.text
        assert "门禁未通过" in blocked.json()["detail"]

        non_pass = client.post(
            f"{API}/maturity/gates",
            json={
                "project_id": project_id,
                "stage_no": 1,
                "conclusion": "PATCH",
                "evidence_url": "https://example.com/gate-review.pdf",
                "exit_criteria": "补齐 Owner",
            },
        )
        assert non_pass.status_code == 201, non_pass.text
        assert non_pass.json()["conclusion_label"] == "修补后通过"
        assert (
            client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2}).status_code
            == 400
        )

        passed = client.post(
            f"{API}/maturity/gates",
            json={
                "project_id": project_id,
                "stage_no": 1,
                "conclusion": "PASS",
                "evidence_url": "https://example.com/gate-pass.pdf",
            },
        )
        assert passed.status_code == 201, passed.text

        advanced = client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2})
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["current_stage"] == 2

        gates = client.get(f"{API}/maturity/gates", params={"project_id": project_id}).json()
        assert any(row["conclusion"] == "PASS" for row in gates)
    finally:
        assert client.delete(f"{API}/projects/{project_id}").status_code == 200
