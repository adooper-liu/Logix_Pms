"""数据治理：数据域/数据流登记、缺口扫描与删除保护。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _user_id(client) -> int:
    return client.get(f"{API}/execution/assignees").json()[0]["id"]


def _domain_payload(client, **overrides) -> dict:
    payload = {
        "name": "测试数据域-" + uuid.uuid4().hex[:6],
        "domain_type": "OTHER",
        "owner_user_id": _user_id(client),
        "description": "测试用",
    }
    payload.update(overrides)
    return payload


def _flow_payload(domain_id: int, **overrides) -> dict:
    payload = {
        "name": "测试数据流-" + uuid.uuid4().hex[:6],
        "domain_id": domain_id,
        "source_system": "ERP",
        "target_system": "BI",
        "frequency": "DAILY",
        "primary_key": "test_code",
        "quality_rule": "主键唯一；每日对账",
        "purpose": "测试",
    }
    payload.update(overrides)
    return payload


def test_seeded_domains_flows_and_summary(client):
    domains = client.get(f"{API}/data-governance/domains").json()
    by_code = {row["code"]: row for row in domains}
    assert {"DD-001", "DD-002", "DD-003", "DD-004", "DD-005"} <= set(by_code)
    assert by_code["DD-001"]["domain_type_label"] == "客户"
    assert by_code["DD-001"]["owner_name"] == "系统管理员"
    assert by_code["DD-001"]["steward_name"] == "流程管理科"
    assert by_code["DD-001"]["flow_count"] == 1

    flows = client.get(f"{API}/data-governance/flows").json()
    by_flow = {row["code"]: row for row in flows}
    assert {"DF-001", "DF-002", "DF-003"} <= set(by_flow)
    first = by_flow["DF-001"]
    assert first["domain_name"] == "客户主数据"
    assert first["frequency_label"] == "每日"
    assert first["process_code"] == "L3-061"
    assert first["quality_rule"]

    summary = client.get(f"{API}/data-governance/summary").json()
    assert summary["domains"] == 5
    assert summary["flows"] == 3
    assert summary["domains_without_owner"] == 0
    assert summary["flows_without_quality_rule"] == 0
    assert summary["flows_without_source"] == 0
    assert summary["flows_without_primary_key"] == 0

    meta = client.get(f"{API}/data-governance/meta").json()
    assert meta["domain_type_labels"]["CUSTOMER"] == "客户"
    assert meta["frequency_labels"]["REAL_TIME"] == "实时"


def test_domain_requires_owner_and_scan_reacts(client):
    rejected = client.post(
        f"{API}/data-governance/domains",
        json={"name": "无主数据域", "domain_type": "OTHER"},
    )
    assert rejected.status_code == 400
    assert "数据所有者" in rejected.json()["detail"]

    created = client.post(f"{API}/data-governance/domains", json=_domain_payload(client))
    assert created.status_code == 201, created.text
    domain = created.json()
    did = domain["id"]

    # 清空所有者 → 扫描生成 HIGH 待办
    cleared = client.patch(f"{API}/data-governance/domains/{did}", json={"owner_user_id": None})
    assert cleared.status_code == 200, cleared.text
    client.post(f"{API}/baselines/audit-scan")
    findings = client.get(
        f"{API}/baselines/findings", params={"type": "DATA_DOMAIN_NO_OWNER"}
    ).json()
    row = next(item for item in findings if item["entity_id"] == did)
    assert row["status"] == "OPEN"
    assert row["severity"] == "HIGH"

    # 补回所有者 → 扫描自动关闭
    assert (
        client.patch(
            f"{API}/data-governance/domains/{did}",
            json={"owner_user_id": _user_id(client)},
        ).status_code
        == 200
    )
    client.post(f"{API}/baselines/audit-scan")
    findings = client.get(
        f"{API}/baselines/findings", params={"type": "DATA_DOMAIN_NO_OWNER"}
    ).json()
    assert next(item for item in findings if item["entity_id"] == did)["status"] == "RESOLVED"

    assert client.delete(f"{API}/data-governance/domains/{did}").status_code == 200


def test_flow_registration_and_incomplete_scan(client):
    domain = client.post(f"{API}/data-governance/domains", json=_domain_payload(client)).json()
    did = domain["id"]
    try:
        created = client.post(f"{API}/data-governance/flows", json=_flow_payload(did))
        assert created.status_code == 201, created.text
        flow = created.json()
        assert flow["domain_name"] == domain["name"]
        assert flow["frequency_label"] == "每日"

        # 允许先登记后补齐；扫描标记缺少质量规则
        incomplete = client.post(
            f"{API}/data-governance/flows",
            json=_flow_payload(did, quality_rule=None),
        )
        assert incomplete.status_code == 201, incomplete.text
        fid = incomplete.json()["id"]
        client.post(f"{API}/baselines/audit-scan")
        findings = client.get(
            f"{API}/baselines/findings", params={"type": "DATA_FLOW_INCOMPLETE"}
        ).json()
        row = next(item for item in findings if item["entity_id"] == fid)
        assert row["status"] == "OPEN"
        assert "质量规则" in row["detail"]

        # 数据域仍有数据流时不能删除
        blocked = client.delete(f"{API}/data-governance/domains/{did}")
        assert blocked.status_code == 409
        assert "数据流" in blocked.json()["detail"]

        assert client.delete(f"{API}/data-governance/flows/{fid}").status_code == 200
        assert client.delete(f"{API}/data-governance/flows/{flow['id']}").status_code == 200
    finally:
        client.delete(f"{API}/data-governance/domains/{did}")


def test_flow_reference_validation(client):
    domain = client.post(f"{API}/data-governance/domains", json=_domain_payload(client)).json()
    try:
        bad_process = client.post(
            f"{API}/data-governance/flows",
            json=_flow_payload(domain["id"], process_id=999999),
        )
        assert bad_process.status_code == 400
        assert "流程" in bad_process.json()["detail"]

        bad_kpi = client.post(
            f"{API}/data-governance/flows",
            json=_flow_payload(domain["id"], kpi_id=999999),
        )
        assert bad_kpi.status_code == 400
        assert "KPI" in bad_kpi.json()["detail"]
    finally:
        client.delete(f"{API}/data-governance/domains/{domain['id']}")


def test_viewer_cannot_manage_data_governance(viewer_client):
    assert (
        viewer_client.post(
            f"{API}/data-governance/domains",
            json={"name": "只读数据域", "domain_type": "OTHER"},
        ).status_code
        == 403
    )
