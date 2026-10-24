"""治理概览：资产有效性、落后变体、固定旧版交付物、基线覆盖率与模板使用。"""

from __future__ import annotations

import uuid

API = "/api/v1"
BYTES = b"PK\x03\x04" + b"governance asset"


def _orgs(client) -> dict:
    return {row["code"]: row for row in client.get(f"{API}/org-units").json()}


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _doc(client, process_id, title, org_unit_id=None) -> dict:
    payload = {"process_id": process_id, "title": title, "category": "SOP"}
    if org_unit_id is not None:
        payload["org_unit_id"] = org_unit_id
    r = client.post(f"{API}/process-documents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _serve_doc(client, document_id, label, valid_from="2026-01-01") -> dict:
    r = client.post(
        f"{API}/process-documents/{document_id}/versions/upload",
        files={"file": (f"g{label}.docx", BYTES, "application/octet-stream")},
        data={"version_label": label, "valid_from": valid_from},
    )
    assert r.status_code == 201, r.text
    version = r.json()
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = client.post(
            f"{API}/process-documents/{document_id}/versions/{version['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text
    return version


def _template(client, name) -> dict:
    r = client.post(
        f"{API}/tool-templates",
        json={"tool_code": "KB", "name": name, "format": "XLSX"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _serve_template(client, template_id) -> dict:
    r = client.post(
        f"{API}/tool-templates/{template_id}/versions/upload",
        files={"file": ("gov.xlsx", BYTES, "application/octet-stream")},
        data={"version_label": "1.0.0"},
    )
    assert r.status_code == 201, r.text
    version = r.json()
    for target in ("IN_REVIEW", "APPROVED", "EFFECTIVE"):
        r = client.post(
            f"{API}/tool-templates/{template_id}/versions/{version['id']}/transition",
            json={"status": target},
        )
        assert r.status_code == 200, r.text
    return version


def test_governance_summary(client, manager_client):
    orgs = _orgs(client)
    process_id = _process_id(client)

    base = _doc(manager_client, process_id, "治理概览集团 SOP", orgs["GROUP-001"]["id"])
    old_version = _serve_doc(manager_client, base["id"], "1.0")

    # 通过正确的创建 payload 建立变体
    v = manager_client.post(
        f"{API}/process-documents",
        json={
            "process_id": process_id,
            "title": "治理概览华东变体",
            "category": "SOP",
            "org_unit_id": orgs["CO-EAST"]["id"],
            "variant_of_document_id": base["id"],
        },
    )
    assert v.status_code == 201, v.text
    variant_doc = v.json()
    _serve_doc(manager_client, variant_doc["id"], "1.0")

    # 项目复制旧版并审批 → 固定旧版
    project = client.post(
        f"{API}/projects",
        json={
            "name": "治理概览测试项目",
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": process_id,
            "start_date": "2026-10-01",
            "end_date": "2027-03-31",
        },
    ).json()
    instance = next(
        row
        for row in client.get(f"{API}/projects/{project['id']}/deliverables").json()
        if row["step_no"] == "2.1"
    )
    copied = manager_client.post(
        f"{API}/process-documents/{base['id']}/versions/{old_version['id']}/copy-to-deliverable",
        json={"deliverable_instance_id": instance["id"]},
    ).json()
    for target in ("IN_REVIEW", "APPROVED"):
        manager_client.post(
            f"{API}/deliverables/{instance['id']}/versions/{copied['id']}/transition",
            json={"status": target},
        )

    # 基线（流程范围）在升级前创建，后续差异应包含 CHANGED
    r = manager_client.post(
        f"{API}/baselines",
        json={"name": "治理概览流程基线", "scope": "PROCESS", "process_id": process_id},
    )
    assert r.status_code == 201, r.text

    # 上级发新版本 → 变体落后
    _serve_doc(manager_client, base["id"], "1.1", "2026-10-01")

    template = _template(manager_client, "治理概览模板")
    template_version = _serve_template(manager_client, template["id"])
    assert (
        client.get(
            f"{API}/tool-templates/{template['id']}/versions/{template_version['id']}/download"
        ).status_code
        == 200
    )

    summary = client.get(f"{API}/baselines/governance").json()
    assert summary["documents_total"] >= 2
    assert summary["documents_effective"] >= 2
    assert summary["variants_total"] >= 1
    assert summary["variants_stale"] >= 1
    assert any(item["document_id"] == variant_doc["id"] for item in summary["stale_variants"])
    assert summary["frozen_references"] >= 1
    assert any(item["project_code"] == project["code"] for item in summary["frozen_items"])
    assert summary["baselines_total"] >= 1
    assert summary["latest_diff"].get("CHANGED", 0) >= 1
    assert summary["processes_total"] >= 1
    assert summary["processes_covered"] >= 1
    assert summary["process_coverage_pct"] > 0
    assert summary["templates_total"] >= 1
    assert summary["templates_effective"] >= 1
    assert summary["template_usage_30d"] >= 1

    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200


def test_kpi_over_cap_creates_governance_finding(client):
    """每条流程的 KPI 超过 5 个时，治理扫描应生成待办。"""
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-KCAP", "name": "KPI 上限测试", "level": 3},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    try:
        for index in range(6):
            kpi = client.post(
                f"{API}/monitor/kpis",
                json={
                    "code": f"CAP-{uuid.uuid4().hex[:6].upper()}-{index}",
                    "name": f"上限测试指标 {index}",
                    "dimension": "EFFICIENCY",
                    "kind": "PROCESS",
                    "direction": "LOWER_BETTER",
                    "process_id": pid,
                    "formula": "A ÷ B",
                    "target_value": 5,
                    "red_threshold": 10,
                    "yellow_threshold": 8,
                    "green_threshold": 5,
                },
            )
            assert kpi.status_code == 201, kpi.text

        scan = client.post(f"{API}/baselines/audit-scan")
        assert scan.status_code == 200, scan.text

        findings = client.get(
            f"{API}/baselines/findings",
            params={"type": "KPI_OVER_CAP", "status": "OPEN"},
        ).json()
        row = next(
            item
            for item in findings
            if item["entity_type"] == "process" and item["entity_id"] == pid
        )
        assert row["severity"] == "MEDIUM"
        assert row["type_label"] == "KPI 数量超限"
        assert "6" in row["detail"]
    finally:
        client.delete(f"{API}/process-map/{pid}")
