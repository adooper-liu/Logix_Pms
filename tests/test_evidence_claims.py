"""项目判断的主张、反证、证据与裁决闭环。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _project(client) -> dict:
    response = client.post(
        f"{API}/projects",
        json={
            "name": "证据链测试 " + uuid.uuid4().hex[:6],
            "methodology": "BPI",
            "owner": "流程管理科",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _claim(client, project_id: int, evidence_type: str, level: str = "L1") -> dict:
    response = client.post(
        f"{API}/projects/{project_id}/claims",
        json={
            "claim": "审批等待是周期过长的主要原因",
            "counterevidence": "样本中存在审批时间短但总周期仍长的订单",
            "evidence_level": level,
            "evidence_type": evidence_type,
            "source_description": f"{evidence_type} 记录",
            "source_url": f"https://example.com/{evidence_type.lower()}",
            "sample_scope": "最近30天，20个订单",
            "finding": "审批耗时占总周期约15%",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_claim_requires_independent_verdict_and_l1_to_l3_evidence(client, manager_client):
    project = _project(client)
    project_id = project["id"]
    try:
        first = _claim(client, project_id, "OBSERVATION")
        second = _claim(client, project_id, "SYSTEM_LOG", "L2")
        assert first["verdict"] == second["verdict"] == "PENDING"

        payload = {"verdict": "CONFIRMED", "decision_note": "证据支持该判断"}
        self_review = client.patch(
            f"{API}/projects/{project_id}/claims/{first['id']}",
            json=payload,
        )
        assert self_review.status_code == 400
        assert "独立复核" in self_review.json()["detail"]

        for claim in (first, second):
            confirmed = manager_client.patch(
                f"{API}/projects/{project_id}/claims/{claim['id']}",
                json=payload,
            )
            assert confirmed.status_code == 200, confirmed.text
            assert confirmed.json()["verdict"] == "CONFIRMED"
            assert confirmed.json()["decided_by"] == "流程管理科"

        workbench = client.get(f"{API}/projects/{project_id}/workflow")
        assert workbench.status_code == 200, workbench.text
        claims = workbench.json()["claims"]
        assert {row["id"] for row in claims} == {first["id"], second["id"]}
    finally:
        client.delete(f"{API}/projects/{project_id}")


def test_l4_or_l5_evidence_cannot_confirm_a_claim(client, manager_client):
    project = _project(client)
    project_id = project["id"]
    try:
        claim = _claim(client, project_id, "INDUSTRY_BENCHMARK", "L4")
        response = manager_client.patch(
            f"{API}/projects/{project_id}/claims/{claim['id']}",
            json={"verdict": "CONFIRMED", "decision_note": "仅有外部对标"},
        )
        assert response.status_code == 400
        assert "L4-L5" in response.json()["detail"]
    finally:
        client.delete(f"{API}/projects/{project_id}")


def test_diagnosis_gate_requires_two_confirmed_evidence_types(client, manager_client):
    project = _project(client)
    project_id = project["id"]
    try:
        workbench = client.get(f"{API}/projects/{project_id}/workflow").json()
        for condition in workbench["gate"]["conditions"]:
            response = client.patch(
                f"{API}/projects/{project_id}/workflow/conditions/{condition['id']}",
                json={"is_met": True, "evidence": "项目范围与基线材料"},
            )
            assert response.status_code == 200, response.text
        for step in workbench["steps"]:
            response = client.patch(
                f"{API}/projects/{project_id}/workflow/steps/{step['id']}",
                json={"status": "DONE", "evidence": ["阶段一交付物"]},
            )
            assert response.status_code == 200, response.text
        advanced = client.post(f"{API}/projects/{project_id}/workflow/advance")
        assert advanced.status_code == 200, advanced.text

        diagnosis = client.get(f"{API}/projects/{project_id}/workflow").json()
        root_gate = next(
            row
            for row in diagnosis["gate"]["conditions"]
            if row["condition_code"] == "ROOT_CAUSE_EVIDENCE"
        )
        blocked = client.patch(
            f"{API}/projects/{project_id}/workflow/conditions/{root_gate['id']}",
            json={"is_met": True, "evidence": "只有口头判断"},
        )
        assert blocked.status_code == 400
        assert "两类" in blocked.json()["detail"]

        for claim in (
            _claim(client, project_id, "OBSERVATION"),
            _claim(client, project_id, "SYSTEM_LOG", "L2"),
        ):
            confirmed = manager_client.patch(
                f"{API}/projects/{project_id}/claims/{claim['id']}",
                json={"verdict": "CONFIRMED", "decision_note": "数据复核支持该判断"},
            )
            assert confirmed.status_code == 200, confirmed.text

        accepted = client.patch(
            f"{API}/projects/{project_id}/workflow/conditions/{root_gate['id']}",
            json={"is_met": True, "evidence": "现场观察与系统日志相互印证"},
        )
        assert accepted.status_code == 200, accepted.text
    finally:
        client.delete(f"{API}/projects/{project_id}")
