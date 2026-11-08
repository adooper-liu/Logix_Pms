"""客户/市场要求与目标承接工作台。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _l3(client):
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == "L3-032")


def test_requirement_crud_and_alignment(client, viewer_client):
    process = _l3(client)
    year = 2026
    suffix = uuid.uuid4().hex[:6].upper()
    created = client.post(
        f"{API}/strategy/objectives",
        json={
            "name": f"承接测试目标-{suffix}",
            "year": year,
            "baseline_value": 14,
            "target_value": 5,
            "unit": "天",
            "owner": "测试 Owner",
        },
    )
    assert created.status_code == 201, created.text
    objective_id = created.json()["id"]
    requirement_id = None
    try:
        linked = client.post(
            f"{API}/strategy/objectives/{objective_id}/links",
            json={"process_id": process["id"]},
        )
        assert linked.status_code == 201, linked.text

        forbidden = viewer_client.post(
            f"{API}/requirements",
            json={
                "source_type": "CUSTOMER",
                "title": "只读不能登记",
                "requirement": "应被拒绝",
            },
        )
        assert forbidden.status_code == 403

        bad_objective = client.post(
            f"{API}/requirements",
            json={
                "source_type": "CUSTOMER",
                "title": "无主要求",
                "requirement": "目标不存在",
                "objective_ids": [99999999],
            },
        )
        assert bad_objective.status_code == 400

        requirement = client.post(
            f"{API}/requirements",
            json={
                "source_type": "CUSTOMER",
                "title": f"客户要求-{suffix}",
                "requirement": "采购需求必须在 5 天内完成审批",
                "evidence_url": "https://example.com/customer-requirement.pdf",
                "objective_ids": [objective_id],
            },
        )
        assert requirement.status_code == 201, requirement.text
        body = requirement.json()
        requirement_id = body["id"]
        assert body["code"].startswith("REQ-")
        assert body["source_label"] == "客户要求"
        assert body["objectives"][0]["id"] == objective_id

        duplicate = client.post(
            f"{API}/requirements",
            json={
                "code": body["code"],
                "source_type": "MARKET",
                "title": "重复编码",
                "requirement": "应被拒绝",
            },
        )
        assert duplicate.status_code == 409

        listed = client.get(f"{API}/requirements", params={"year": year})
        assert listed.status_code == 200, listed.text
        assert any(row["id"] == requirement_id for row in listed.json())

        aligned = client.get(f"{API}/alignment", params={"year": year})
        assert aligned.status_code == 200, aligned.text
        data = aligned.json()
        row = next(item for item in data["objectives"] if item["id"] == objective_id)
        assert any(item["id"] == requirement_id for item in row["requirements"])
        assert row["processes"][0]["id"] == process["id"]
        keys = {item["key"] for item in row["enablers"]}
        assert keys == {"RESOURCE", "TEAM", "PROCESS", "SYSTEM"}
        assert all(item["label"] for item in row["enablers"])
        assert any("未关联客户/市场要求" not in gap for gap in row["gaps"])
        assert data["summary"]["requirements"] >= 1
        assert "RESOURCE" in data["summary"]["enabler_ready"]

        updated = client.patch(
            f"{API}/requirements/{requirement_id}",
            json={"status": "CLOSED", "objective_ids": []},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["status"] == "CLOSED"
        assert updated.json()["objectives"] == []

        aligned = client.get(f"{API}/alignment", params={"year": year}).json()
        row = next(item for item in aligned["objectives"] if item["id"] == objective_id)
        assert not row["requirements"]
        assert any("未关联客户/市场要求" in gap for gap in row["gaps"])
    finally:
        if requirement_id:
            client.delete(f"{API}/requirements/{requirement_id}")
        client.delete(f"{API}/strategy/objectives/{objective_id}")
