"""标准工时与产能：计算口径、验证门禁、产能利用率与实际工时归集。"""

from __future__ import annotations

API = "/api/v1"


def _l4(client) -> dict:
    rows = client.get(f"{API}/process-map/flat", params={"level": 4}).json()
    assert rows
    return rows[0]


def _position(client, name: str | None = None) -> dict:
    rows = client.get(f"{API}/positions").json()
    assert rows
    if name is None:
        return rows[0]
    return next(row for row in rows if row["name"] == name)


def _standard_payload(client, **overrides) -> dict:
    activity = _l4(client)
    position = _position(client)
    payload = {
        "name": "测试标准工时",
        "activity_id": activity["id"],
        "position_id": position["id"],
        "method_description": "测试方法：取料→处理→放行",
        "source": "TIME_STUDY",
        "observed_minutes": 10.0,
        "rating_factor": 1.1,
        "allowance_rate": 0.1,
        "sample_size": 5,
        "monthly_frequency": 10.0,
        "valid_from": "2026-01-01",
    }
    payload.update(overrides)
    return payload


def test_seeded_standards_capacity_and_summary(client):
    standards = client.get(f"{API}/workload/standards").json()
    by_code = {row["code"]: row for row in standards}
    assert {"WS-2026-001", "WS-2026-002", "WS-2026-003", "WS-2026-004"} <= set(by_code)
    assert by_code["WS-2026-001"]["standard_minutes"] == 52.92  # 45 × 1.05 × 1.12
    assert by_code["WS-2026-001"]["status"] == "VERIFIED"
    assert by_code["WS-2026-001"]["source_label"] == "时间研究"
    assert by_code["WS-2026-005"]["status"] == "DRAFT"
    assert by_code["WS-2026-005"]["source_label"] == "估算（未验证）"

    capacity = client.get(f"{API}/workload/capacity", params={"period": "2026-10-01"}).json()
    assert len(capacity) == 3
    proc = next(row for row in capacity if row["org_unit_name"] == "采购部")
    assert proc["available_minutes"] == 38304.0  # 4 × 168 × 60 × 0.95

    summary = client.get(f"{API}/workload/summary", params={"period": "2026-10-01"}).json()
    assert summary["period"] == "2026-10-01"
    assert len(summary["standards"]) == 5
    assert sum(1 for row in summary["standards"] if row["included"]) == 4
    # 只有 4 条已验证标准进入需求工时；估算的 WS-005 不计入
    assert summary["totals"]["demand_minutes"] == 13543.2
    assert summary["totals"]["available_minutes"] == 84672.0
    assert abs(summary["totals"]["utilization"] - 0.16) < 0.001

    demand_by_position = {
        row["position_name"]: row["demand_minutes"] for row in summary["capacity"]
    }
    assert demand_by_position["采购计划员"] == 10389.6
    assert demand_by_position["预算会计"] == 2376.0
    assert demand_by_position["部门负责人"] == 777.6


def test_create_verify_and_invalidate_standard(client):
    created = client.post(f"{API}/workload/standards", json=_standard_payload(client))
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["standard_minutes"] == 12.1  # 10 × 1.1 × 1.1
    assert data["status"] == "DRAFT"
    assert data["version"] == 1
    sid = data["id"]

    verified = client.post(f"{API}/workload/standards/{sid}/verify")
    assert verified.status_code == 200, verified.text
    assert verified.json()["status"] == "VERIFIED"
    assert verified.json()["verified_by_name"] == "系统管理员"

    # 改口径会自动升版并回到草稿，必须重新验证
    updated = client.patch(f"{API}/workload/standards/{sid}", json={"observed_minutes": 12.0})
    assert updated.status_code == 200, updated.text
    assert updated.json()["standard_minutes"] == 14.52  # 12 × 1.1 × 1.1
    assert updated.json()["version"] == 2
    assert updated.json()["status"] == "DRAFT"
    assert updated.json()["verified_by_id"] is None


def test_estimate_cannot_be_verified(client):
    created = client.post(
        f"{API}/workload/standards",
        json=_standard_payload(
            client,
            source="ESTIMATE",
            sample_size=0,
            method_description=None,
        ),
    )
    assert created.status_code == 201, created.text
    rejected = client.post(f"{API}/workload/standards/{created.json()['id']}/verify")
    assert rejected.status_code == 400
    assert "估算" in rejected.json()["detail"]


def test_capacity_rules(client):
    capacity = client.get(f"{API}/workload/capacity", params={"period": "2026-10-01"}).json()
    existing = next(row for row in capacity if row["org_unit_name"] == "采购部")
    duplicate = client.post(
        f"{API}/workload/capacity",
        json={
            "org_unit_id": existing["org_unit_id"],
            "position_id": existing["position_id"],
            "period": "2026-10-01",
            "headcount": 1,
            "available_hours_per_person": 160,
            "attendance_rate": 1,
            "equipment_availability": 1,
        },
    )
    assert duplicate.status_code == 400
    assert "已有产能记录" in duplicate.json()["detail"]

    other_org = next(row for row in capacity if row["org_unit_name"] == "财务部")
    mismatch = client.post(
        f"{API}/workload/capacity",
        json={
            "org_unit_id": other_org["org_unit_id"],
            "position_id": existing["position_id"],
            "period": "2026-12-01",
            "headcount": 1,
            "available_hours_per_person": 160,
            "attendance_rate": 1,
            "equipment_availability": 1,
        },
    )
    assert mismatch.status_code == 400
    assert "不属于" in mismatch.json()["detail"]

    created = client.post(
        f"{API}/workload/capacity",
        json={
            "org_unit_id": existing["org_unit_id"],
            "position_id": existing["position_id"],
            "period": "2026-11-01",
            "headcount": 2,
            "available_hours_per_person": 160,
            "attendance_rate": 0.9,
            "equipment_availability": 0.95,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["period"] == "2026-11-01"
    assert created.json()["available_minutes"] == 2 * 160 * 60 * 0.9 * 0.95


def test_summary_excludes_draft_demand(client):
    before = client.get(f"{API}/workload/summary", params={"period": "2026-10-01"}).json()
    created = client.post(
        f"{API}/workload/standards",
        json=_standard_payload(client, monthly_frequency=1000.0, observed_minutes=100.0),
    )
    assert created.status_code == 201, created.text
    after = client.get(f"{API}/workload/summary", params={"period": "2026-10-01"}).json()
    assert after["totals"]["demand_minutes"] == before["totals"]["demand_minutes"]
    draft = next(row for row in after["standards"] if row["standard_id"] == created.json()["id"])
    assert draft["included"] is False


def test_actual_worklog_is_attributed_to_activity(client):
    process = next(
        row for row in client.get(f"{API}/execution/processes").json() if row["code"] == "L3-032"
    )
    instance = client.post(
        f"{API}/execution/instances", json={"process_id": process["id"], "variables": {}}
    )
    assert instance.status_code == 201, instance.text
    iid = instance.json()["id"]
    try:
        before = client.get(f"{API}/workload/summary").json()["totals"]["actual_minutes"]
        task = client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        done = client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={
                "form_data": {"applicant": "工时测试", "amount": 1000},
                "effort_minutes": 37.5,
            },
        )
        assert done.status_code == 200, done.text
        summary = client.get(f"{API}/workload/summary").json()
        assert summary["totals"]["actual_minutes"] - before >= 37.5
        row = next(item for item in summary["actual"] if item["effort_minutes"] >= 37.5)
        assert row["activity_id"] is not None
        assert row["activity_name"]
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


def test_viewer_cannot_write(viewer_client):
    r = viewer_client.post(f"{API}/workload/standards", json=_standard_payload(viewer_client))
    assert r.status_code == 403
