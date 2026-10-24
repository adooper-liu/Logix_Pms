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


def test_meta_declares_work_measurement_boundary(client):
    """标准工时的边界必须由后端下发，页面不能自己写一套口径。"""
    meta = client.get(f"{API}/workload/meta").json()
    note = meta["boundary_note"]
    assert "能力基线" in note
    assert "不用于个人" in note
    assert "扣罚" in note
    assert "已验证" in note


def _observation(standard_id: int, minutes: float, **overrides) -> dict:
    payload = {
        "observed_minutes": minutes,
        "observed_at": "2026-11-01T09:00:00",
        "note": "现场观测",
    }
    payload.update(overrides)
    return payload


def test_time_study_observation_and_review_flow(client):
    created = client.post(
        f"{API}/workload/standards",
        json=_standard_payload(client, sample_size=0),
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    assert created.json()["observation_count"] == 0

    for minutes in (10.0, 12.0, 11.0, 13.0, 9.0):
        added = client.post(
            f"{API}/workload/standards/{sid}/observations", json=_observation(sid, minutes)
        )
        assert added.status_code == 201, added.text
    standards = client.get(f"{API}/workload/standards").json()
    row = next(item for item in standards if item["id"] == sid)
    assert row["observation_count"] == 5
    assert row["sample_size"] == 5
    assert row["observed_minutes"] == 11.0
    assert row["standard_minutes"] == 13.31

    observations = client.get(f"{API}/workload/standards/{sid}/observations").json()
    assert [item["sequence"] for item in observations] == [1, 2, 3, 4, 5]
    assert observations[0]["observer_name"] == "系统管理员"

    submitted = client.post(f"{API}/workload/standards/{sid}/submit-review")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "IN_REVIEW"
    assert submitted.json()["status_label"] == "待审核"

    approved = client.post(
        f"{API}/workload/standards/{sid}/review",
        json={"approved": True, "note": "方法与样本符合要求"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "VERIFIED"
    assert approved.json()["reviewed_by_name"] == "系统管理员"
    assert approved.json()["review_note"] == "方法与样本符合要求"

    # 已验证后新增样本：重新回到草稿并升版
    sixth = client.post(f"{API}/workload/standards/{sid}/observations", json=_observation(sid, 8.0))
    assert sixth.status_code == 201
    after_add = next(
        item for item in client.get(f"{API}/workload/standards").json() if item["id"] == sid
    )
    assert after_add["status"] == "DRAFT"
    assert after_add["version"] == 2
    assert after_add["sample_size"] == 6
    assert after_add["observed_minutes"] == 10.5
    assert after_add["reviewed_by_id"] is None

    # 退回必须写原因
    assert client.post(f"{API}/workload/standards/{sid}/submit-review").status_code == 200
    rejected = client.post(
        f"{API}/workload/standards/{sid}/review", json={"approved": False, "note": ""}
    )
    assert rejected.status_code == 400
    returned = client.post(
        f"{API}/workload/standards/{sid}/review",
        json={"approved": False, "note": "样本波动偏大，请补充观测"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "DRAFT"
    assert returned.json()["review_note"] == "样本波动偏大，请补充观测"

    # 删除一条观测后自动回算
    obs_id = observations[0]["id"]
    assert client.delete(f"{API}/workload/standards/{sid}/observations/{obs_id}").status_code == 200
    after_delete = next(
        item for item in client.get(f"{API}/workload/standards").json() if item["id"] == sid
    )
    assert after_delete["observation_count"] == 5
    assert after_delete["sample_size"] == 5


def test_submit_review_requires_samples(client):
    created = client.post(
        f"{API}/workload/standards",
        json=_standard_payload(client, sample_size=0),
    )
    sid = created.json()["id"]
    response = client.post(f"{API}/workload/standards/{sid}/submit-review")
    assert response.status_code == 400
    assert "样本不足" in response.json()["detail"]


def test_observations_lock_manual_mean(client):
    created = client.post(
        f"{API}/workload/standards",
        json=_standard_payload(client, sample_size=0),
    )
    sid = created.json()["id"]
    assert (
        client.post(
            f"{API}/workload/standards/{sid}/observations", json=_observation(sid, 10.0)
        ).status_code
        == 201
    )
    rejected = client.patch(f"{API}/workload/standards/{sid}", json={"observed_minutes": 12.0})
    assert rejected.status_code == 400
    assert "已有观测记录" in rejected.json()["detail"]


def test_observation_permissions(owner_client, viewer_client):
    standards = owner_client.get(f"{API}/workload/standards").json()
    sid = standards[0]["id"]
    assert (
        owner_client.post(
            f"{API}/workload/standards/{sid}/observations", json=_observation(sid, 10.0)
        ).status_code
        == 403
    )
    assert (
        viewer_client.post(
            f"{API}/workload/standards/{sid}/observations", json=_observation(sid, 10.0)
        ).status_code
        == 403
    )
    # 读取观测记录对只读角色开放
    assert viewer_client.get(f"{API}/workload/standards/{sid}/observations").status_code == 200
