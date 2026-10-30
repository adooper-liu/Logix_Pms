"""改善项目卡：KPI 越线立项、去重、字段维护与复制状态。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _kpi(client, code: str) -> dict:
    rows = client.get(f"{API}/monitor/kpis").json()
    return next(row for row in rows if row["code"] == code)


def _draft(client, kpi_id: int):
    return client.post(f"{API}/monitor/kpis/{kpi_id}/improvement-draft")


def _seed_reimbursement(client) -> dict:
    """费用报销种子项目与 EFF-05 同一口径，进行中时不应再平行立项。"""
    listing = client.get(f"{API}/projects", params={"keyword": "费用报销"}).json()
    return next(row for row in listing["items"] if row["code"] == "PR-2026-029")


def test_candidates_scan_and_exclusion(client):
    kpi = _kpi(client, "EFF-05")
    seed = _seed_reimbursement(client)
    assert seed["source_kpi_id"] == kpi["id"]
    rows = client.get(f"{API}/monitor/improvement-candidates").json()
    assert "EFF-05" not in {row["code"] for row in rows}

    closed = client.patch(f"{API}/projects/{seed['id']}", json={"status": "CLOSED"})
    assert closed.status_code == 200, closed.text
    rows = client.get(f"{API}/monitor/improvement-candidates").json()
    assert "EFF-05" in {row["code"] for row in rows}
    candidate = next(row for row in rows if row["code"] == "EFF-05")
    assert candidate["status"] == "RED"
    assert candidate["status_label"] == "红"

    created = _draft(client, kpi["id"])
    assert created.status_code == 201, created.text
    rows = client.get(f"{API}/monitor/improvement-candidates").json()
    assert "EFF-05" not in {row["code"] for row in rows}
    client.delete(f"{API}/projects/{created.json()['id']}")
    client.patch(f"{API}/projects/{seed['id']}", json={"status": "PLANNING"})


def test_red_kpi_creates_improvement_project(client):
    kpi = _kpi(client, "EFF-05")  # 10 天 > 红线 7.6 → 红
    seed = _seed_reimbursement(client)
    assert (
        client.patch(f"{API}/projects/{seed['id']}", json={"status": "CLOSED"}).status_code == 200
    )
    assert kpi["status"] == "RED"

    created = _draft(client, kpi["id"])
    assert created.status_code == 201, created.text
    project = created.json()
    assert project["source_kpi_id"] == kpi["id"]
    assert project["status"] == "PLANNING"
    assert project["status_label"] == "立项中"
    pid = project["id"]

    detail = client.get(f"{API}/projects/{pid}").json()["project"]
    assert detail["source"] == "KPI_THRESHOLD"
    assert detail["source_label"] == "KPI 越线"
    assert detail["source_kpi_code"] == "EFF-05"
    assert detail["baseline_value"] == kpi["latest_value"]
    assert detail["target_value"] == kpi["target_value"]
    assert detail["priority"] == 1
    assert detail["methodology"] == "BPI"
    assert "红线" in detail["problem_statement"]
    assert detail["replication_status"] == "NOT_EVALUATED"
    assert detail["replication_status_label"] == "未评估"

    steps = client.get(f"{API}/projects/{pid}/steps").json()
    assert len(steps) == 24

    duplicate = _draft(client, kpi["id"])
    assert duplicate.status_code == 409
    assert "已有进行中" in duplicate.json()["detail"]

    updated = client.patch(
        f"{API}/projects/{pid}",
        json={
            "problem_statement": "报销流程等待时间过长",
            "root_cause": "审批人无代理人，退回后需重新提交",
            "countermeasure": "设置 24 小时超时提醒与代理人机制",
            "verification": "连续 4 周周期低于 5 天",
            "benefit": "每月节省 120 人天",
            "observation_until": "2026-12-31",
            "one_time_cost": 5.0,
            "transfer_cost": 1.0,
            "replication_status": "PILOT",
            "replication_note": "先在华东分公司试点",
        },
    )
    assert updated.status_code == 200, updated.text
    data = updated.json()
    assert data["root_cause"].startswith("审批人")
    assert data["replication_status_label"] == "试点中"
    assert data["one_time_cost"] == 5.0
    assert data["observation_until"] == "2026-12-31"

    assert client.delete(f"{API}/projects/{pid}").status_code == 200
    client.patch(f"{API}/projects/{seed['id']}", json={"status": "PLANNING"})


def test_closed_project_allows_new_draft(client):
    kpi = _kpi(client, "EFF-05")
    seed = _seed_reimbursement(client)
    assert (
        client.patch(f"{API}/projects/{seed['id']}", json={"status": "CLOSED"}).status_code == 200
    )
    first = _draft(client, kpi["id"])
    assert first.status_code == 201, first.text
    pid = first.json()["id"]
    assert client.patch(f"{API}/projects/{pid}", json={"status": "CLOSED"}).status_code == 200
    second = _draft(client, kpi["id"])
    assert second.status_code == 201, second.text
    client.delete(f"{API}/projects/{second.json()['id']}")
    client.delete(f"{API}/projects/{pid}")
    client.patch(f"{API}/projects/{seed['id']}", json={"status": "PLANNING"})


def test_green_kpi_is_not_a_candidate(client):
    kpi = _kpi(client, "QUA-02")  # 97.2 ≥ 绿线 97
    assert kpi["status"] == "GREEN"
    rejected = _draft(client, kpi["id"])
    assert rejected.status_code == 400
    assert "红/黄" in rejected.json()["detail"]


def test_kpi_without_data_or_target_is_rejected(client):
    code = "TST-" + uuid.uuid4().hex[:6].upper()
    base = {
        "code": code,
        "name": "无数据测试指标",
        "dimension": "EFFICIENCY",
        "kind": "PROCESS",
        "direction": "LOWER_BETTER",
        "formula": "A ÷ B",
        "red_threshold": 10,
        "yellow_threshold": 8,
        "green_threshold": 5,
    }
    no_data = client.post(f"{API}/monitor/kpis", json=base)
    assert no_data.status_code == 201, no_data.text
    rejected = _draft(client, no_data.json()["id"])
    assert rejected.status_code == 400
    assert "还没有数据" in rejected.json()["detail"]

    no_target = client.post(
        f"{API}/monitor/kpis",
        json={**base, "code": code + "-T", "name": "无目标测试指标", "target_value": None},
    )
    assert no_target.status_code == 201, no_target.text
    kpi_id = no_target.json()["id"]
    assert (
        client.post(
            f"{API}/monitor/kpis/{kpi_id}/records",
            json={"period": "2026-10-01", "value": 12},
        ).status_code
        == 201
    )
    rejected_target = _draft(client, kpi_id)
    assert rejected_target.status_code == 400
    assert "目标值" in rejected_target.json()["detail"]


def test_meta_labels_and_permissions(client, viewer_client):
    meta = client.get(f"{API}/projects/meta").json()
    assert meta["source_labels"]["KPI_THRESHOLD"] == "KPI 越线"
    assert meta["source_labels"]["EXCEPTION"] == "流程异常"
    assert meta["replication_status_labels"]["PILOT"] == "试点中"

    kpi = _kpi(client, "EFF-05")
    r = viewer_client.post(f"{API}/monitor/kpis/{kpi['id']}/improvement-draft")
    assert r.status_code == 403


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)["id"]


def test_exception_creates_improvement_project(client, viewer_client):
    process_id = _process_id(client)
    created = client.post(
        f"{API}/monitor/exceptions",
        json={
            "title": "异常转改善测试",
            "description": "来料检验连续一周积压",
            "severity": "HIGH",
            "process_id": process_id,
            "root_cause": "检验人力未按到货波峰排班",
        },
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]
    # 根因是处理阶段填写的，登记后再补，转换时应一并带到项目卡
    assert (
        client.patch(
            f"{API}/monitor/exceptions/{eid}",
            json={"root_cause": "检验人力未按到货波峰排班"},
        ).status_code
        == 200
    )

    draft = client.post(f"{API}/monitor/exceptions/{eid}/improvement-draft")
    assert draft.status_code == 201, draft.text
    pid = draft.json()["id"]

    exception = client.get(f"{API}/monitor/exceptions/{eid}").json()
    assert exception["project_id"] == pid
    assert exception["status"] == "IN_PROGRESS", "转改善后异常应进入处理中"

    detail = client.get(f"{API}/projects/{pid}").json()["project"]
    assert detail["source"] == "EXCEPTION"
    assert detail["source_label"] == "流程异常"
    assert detail["process_id"] == process_id
    assert detail["priority"] == 1
    assert detail["root_cause"] == "检验人力未按到货波峰排班"
    assert "来料检验连续一周积压" in detail["problem_statement"]
    assert len(client.get(f"{API}/projects/{pid}/steps").json()) == 24

    duplicate = client.post(f"{API}/monitor/exceptions/{eid}/improvement-draft")
    assert duplicate.status_code == 409
    assert "已有进行中" in duplicate.json()["detail"]

    denied = viewer_client.post(f"{API}/monitor/exceptions/{eid}/improvement-draft")
    assert denied.status_code == 403

    assert client.delete(f"{API}/projects/{pid}").status_code == 200
    assert client.delete(f"{API}/monitor/exceptions/{eid}").status_code == 200


def test_closed_exception_cannot_create_improvement(client):
    created = client.post(
        f"{API}/monitor/exceptions",
        json={"title": "已闭环异常测试", "severity": "LOW"},
    ).json()
    eid = created["id"]
    assert (
        client.patch(f"{API}/monitor/exceptions/{eid}", json={"status": "CLOSED"}).status_code
        == 200
    )
    rejected = client.post(f"{API}/monitor/exceptions/{eid}/improvement-draft")
    assert rejected.status_code == 400
    assert "已解决或已闭环" in rejected.json()["detail"]
    assert client.delete(f"{API}/monitor/exceptions/{eid}").status_code == 200
