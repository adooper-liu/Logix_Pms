"""成熟度评估与阶段门禁：证据、覆盖度与阶段推进拦截。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)["id"]


def _new_apqc_process(client, *, add_mapping: bool = True) -> tuple[int, int]:
    rows = client.get(f"{API}/process-map/flat").json()
    parent = next(row for row in rows if row["level"] == 2)
    code = "T-" + uuid.uuid4().hex[:10].upper()
    created = client.post(
        f"{API}/process-map",
        json={
            "code": code,
            "name": "阶段门 APQC 测试流程",
            "level": 3,
            "parent_id": parent["id"],
            "owner": "流程Owner",
            "department": "测试部门",
        },
    )
    assert created.status_code == 201, created.text
    process_id = created.json()["id"]

    framework = next(
        row for row in client.get(f"{API}/benchmark/frameworks").json() if row["code"] == "APQC_PCF"
    )
    tree = client.get(f"{API}/benchmark/frameworks/{framework['code']}/tree?max_level=3").json()
    pending = list(tree)
    category = None
    while pending:
        row = pending.pop()
        if row["level"] == 3:
            category = row
            break
        pending.extend(row.get("children", []))
    assert category is not None, "APQC PCF should contain an L3 process"
    if add_mapping:
        mapping = client.post(
            f"{API}/benchmark/mappings",
            json={"process_id": process_id, "category_id": category["id"]},
        )
        assert mapping.status_code == 201, mapping.text
    return process_id, category["id"]


def _create_project(client, process_id: int) -> dict:
    created = client.post(
        f"{API}/projects",
        json={
            "name": "门禁测试项目",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": process_id,
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
    process_id, _ = _new_apqc_process(client)
    project = _create_project(client, process_id)
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

        workbench = client.get(f"{API}/projects/{project_id}/workflow").json()
        for condition in workbench["gate"]["conditions"]:
            updated = client.patch(
                f"{API}/projects/{project_id}/workflow/conditions/{condition['id']}",
                json={
                    "is_met": True,
                    "evidence": "核验材料-" + str(condition["id"]),
                    "owner": "流程管理科",
                },
            )
            assert updated.status_code == 200, updated.text
        for step in workbench["steps"]:
            updated = client.patch(
                f"{API}/projects/{project_id}/workflow/steps/{step['id']}",
                json={"status": "DONE", "evidence": [f"验收-{step['step_no']}"]},
            )
            assert updated.status_code == 200, updated.text

        advanced = client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2})
        assert advanced.status_code == 200, advanced.text
        assert advanced.json()["current_stage"] == 2

        gates = client.get(f"{API}/maturity/gates", params={"project_id": project_id}).json()
        assert any(row["conclusion"] == "PASS" for row in gates)
    finally:
        assert client.delete(f"{API}/projects/{project_id}").status_code == 200
        assert client.delete(f"{API}/process-map/{process_id}").status_code == 200


def test_strict_gate_requires_apqc_l3_mapping(client):
    process_id, category_id = _new_apqc_process(client, add_mapping=False)
    project = _create_project(client, process_id)
    project_id = project["id"]
    try:
        assert (
            client.patch(f"{API}/projects/{project_id}", json={"gate_required": True}).status_code
            == 200
        )
        signed = client.post(
            f"{API}/maturity/gates",
            json={
                "project_id": project_id,
                "stage_no": 1,
                "conclusion": "PASS",
                "evidence_url": "https://example.com/gate-pass.pdf",
            },
        )
        assert signed.status_code == 201, signed.text
        workbench = client.get(f"{API}/projects/{project_id}/workflow").json()
        for condition in workbench["gate"]["conditions"]:
            response = client.patch(
                f"{API}/projects/{project_id}/workflow/conditions/{condition['id']}",
                json={"is_met": True, "evidence": "核验材料"},
            )
            assert response.status_code == 200, response.text
        for step in workbench["steps"]:
            response = client.patch(
                f"{API}/projects/{project_id}/workflow/steps/{step['id']}",
                json={"status": "DONE", "evidence": ["阶段交付物"]},
            )
            assert response.status_code == 200, response.text

        blocked = client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2})
        assert blocked.status_code == 400
        assert "APQC PCF L1-L3" in blocked.json()["detail"]

        mapped = client.post(
            f"{API}/benchmark/mappings",
            json={"process_id": process_id, "category_id": category_id},
        )
        assert mapped.status_code == 201, mapped.text
        advanced = client.patch(f"{API}/projects/{project_id}", json={"current_stage": 2})
        assert advanced.status_code == 200, advanced.text
    finally:
        assert client.delete(f"{API}/projects/{project_id}").status_code == 200
        assert client.delete(f"{API}/process-map/{process_id}").status_code == 200
