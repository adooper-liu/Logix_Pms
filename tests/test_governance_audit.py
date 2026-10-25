"""一致性审计扫描：治理待办的新增、去重、忽略与自动关闭。"""

from __future__ import annotations

API = "/api/v1"
BYTES = b"PK\x03\x04" + b"audit asset"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _doc(client, process_id, title, **extra) -> dict:
    payload = {"process_id": process_id, "title": title, "category": "SOP", **extra}
    r = client.post(f"{API}/process-documents", json=payload)
    assert r.status_code == 201, r.text
    return r.json()


def _serve_doc(client, document_id, label, valid_from="2026-01-01") -> dict:
    r = client.post(
        f"{API}/process-documents/{document_id}/versions/upload",
        files={"file": (f"a{label}.docx", BYTES, "application/octet-stream")},
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


def _scan(client) -> dict:
    r = client.post(f"{API}/baselines/audit-scan")
    assert r.status_code == 200, r.text
    return r.json()


def _findings(client, **params) -> list:
    return client.get(f"{API}/baselines/findings", params=params).json()


def test_audit_scan_creates_dedupes_ignores_and_resolves(client, manager_client, viewer_client):
    manager_id = manager_client.get(f"{API}/auth/me").json()["id"]
    process_id = _process_id(client)
    orgs = {row["code"]: row for row in client.get(f"{API}/org-units").json()}

    base = _doc(
        manager_client,
        process_id,
        "审计集团 SOP",
        owner_user_id=manager_id,
        org_unit_id=None,
    )
    old_version = _serve_doc(manager_client, base["id"], "1.0")
    variant = _doc(
        manager_client,
        process_id,
        "审计华东变体",
        owner_user_id=manager_id,
        org_unit_id=orgs["CO-EAST"]["id"],
        variant_of_document_id=base["id"],
    )
    _serve_doc(manager_client, variant["id"], "1.0")

    no_effective = _doc(manager_client, process_id, "审计未生效 SOP", owner_user_id=manager_id)
    overdue = manager_client.post(
        f"{API}/tool-templates",
        json={
            "tool_code": "KB",
            "name": "审计复审逾期模板",
            "format": "XLSX",
            "owner_user_id": manager_id,
            "review_date": "2020-01-01",
        },
    ).json()

    project = client.post(
        f"{API}/projects",
        json={
            "name": "审计固定旧版项目",
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

    # 复制完成后上级再发新版：交付物固定旧版、变体落后
    _serve_doc(manager_client, base["id"], "1.1", "2026-10-01")

    assert viewer_client.post(f"{API}/baselines/audit-scan").status_code == 403

    result = _scan(manager_client)
    assert result["created"] >= 4
    assert result["notified"] >= 1

    open_rows = _findings(client, status="OPEN")
    by_entity = {(row["entity_type"], row["entity_id"]): row for row in open_rows}
    stale = by_entity[("process_document", variant["id"])]
    assert stale["type"] == "STALE_VARIANT"
    assert stale["status_label"] == "待处理"
    assert by_entity[("process_document", no_effective["id"])]["type"] == "NO_EFFECTIVE"
    assert by_entity[("tool_template", overdue["id"])]["type"] in {"NO_EFFECTIVE", "REVIEW_OVERDUE"}
    assert any(
        row["entity_id"] == overdue["id"]
        for row in _findings(client, status="OPEN", type="REVIEW_OVERDUE")
    )
    assert any(
        row["type"] == "FROZEN_REFERENCE" and row["entity_id"] == copied["id"] for row in open_rows
    )

    # 通知：责任人收到治理待办（去重后至少一条未读）
    summary = manager_client.get(f"{API}/notifications/summary").json()
    assert summary["by_type"].get("GOVERNANCE_FINDING", 0) >= 1

    # 重复扫描不新增
    again = _scan(manager_client)
    assert again["created"] == 0

    # 忽略后保留但不提醒
    finding_id = by_entity[("process_document", no_effective["id"])]["id"]
    r = manager_client.patch(f"{API}/baselines/findings/{finding_id}", json={"status": "IGNORED"})
    assert r.status_code == 200
    result = _scan(manager_client)
    assert result["ignored"] >= 1
    ignored_rows = _findings(client, status="IGNORED")
    assert any(row["id"] == finding_id for row in ignored_rows)

    # 条件消失 → 自动关闭
    assert (
        client.patch(
            f"{API}/process-documents/{no_effective['id']}", json={"is_active": False}
        ).status_code
        == 200
    )
    result = _scan(manager_client)
    assert result["resolved"] >= 1
    resolved_rows = _findings(client, status="RESOLVED")
    assert any(row["id"] == finding_id for row in resolved_rows)

    assert client.delete(f"{API}/projects/{project['id']}").status_code == 200
