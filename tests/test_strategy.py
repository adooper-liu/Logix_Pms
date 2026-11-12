"""战略目标：承接关系、反查继承与写权限。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process_ids(client) -> dict[str, dict]:
    rows = client.get(f"{API}/process-map/flat").json()
    return {row["code"]: row for row in rows}


def _kpi_ids(client) -> dict[str, dict]:
    rows = client.get(f"{API}/monitor/kpis").json()
    return {row["code"]: row for row in rows}


def _objective_payload(**overrides) -> dict:
    payload = {
        "name": "测试战略目标-" + uuid.uuid4().hex[:6],
        "description": "用于测试的目标",
        "year": 2026,
        "period": "ANNUAL",
        "baseline_value": 10.0,
        "target_value": 5.0,
        "unit": "天",
        "source_document": "测试年度计划",
        "owner": "陈经理",
        "status": "ACTIVE",
    }
    payload.update(overrides)
    return payload


def test_seeded_objectives_and_summary(client):
    rows = client.get(f"{API}/strategy/objectives", params={"year": 2026}).json()
    by_code = {row["code"]: row for row in rows}
    assert set(by_code) == {"OBJ-2026-01"}
    first = by_code["OBJ-2026-01"]
    assert first["period_label"] == "年度"
    assert first["status_label"] == "进行中"
    assert first["process_count"] == 2
    assert first["kpi_count"] == 1
    assert first["owner_user_id"] is not None
    assert {link["process_code"] for link in first["links"]} == {"L3-032", "L4-202"}
    assert any(link["kpi_code"] == "EFF-01" for link in first["links"])

    summary = client.get(f"{API}/strategy/summary", params={"year": 2026}).json()
    assert summary["objective_count"] == 1
    assert summary["active_count"] == 1
    assert summary["linked_count"] == 1
    assert summary["unlinked_count"] == 0
    assert summary["kpi_link_count"] == 1


def test_reverse_lookup_by_process_and_kpi(client):
    processes = _process_ids(client)
    objectives = client.get(
        f"{API}/strategy/processes/{processes['L4-202']['id']}/objectives"
    ).json()
    assert "OBJ-2026-01" in {row["code"] for row in objectives}

    kpis = _kpi_ids(client)
    by_kpi = client.get(f"{API}/strategy/kpis/{kpis['EFF-01']['id']}/objectives").json()
    assert "OBJ-2026-01" in {row["code"] for row in by_kpi}

    missing = client.get(f"{API}/strategy/processes/999999/objectives")
    assert missing.status_code == 404


def test_create_update_and_archive(client):
    # 用已有目标绑定的账号，避免依赖 display_name 唯一（其他用例会造同名账号）
    seed = client.get(f"{API}/strategy/objectives", params={"year": 2026}).json()[0]
    created = client.post(
        f"{API}/strategy/objectives",
        json=_objective_payload(owner=None, owner_user_id=seed["owner_user_id"]),
    )
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["code"].startswith("OBJ-2026-")
    assert data["owner_user_id"] == seed["owner_user_id"]
    oid = data["id"]

    updated = client.patch(
        f"{API}/strategy/objectives/{oid}",
        json={"target_value": 4.0, "status": "ARCHIVED"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["target_value"] == 4.0
    assert updated.json()["status_label"] == "已归档"

    assert client.delete(f"{API}/strategy/objectives/{oid}").status_code == 200
    assert client.get(f"{API}/strategy/objectives/{oid}").status_code == 404


def test_link_rules_and_duplicate_guard(client):
    created = client.post(f"{API}/strategy/objectives", json=_objective_payload()).json()
    oid = created["id"]
    processes = _process_ids(client)
    kpis = _kpi_ids(client)

    link = client.post(
        f"{API}/strategy/objectives/{oid}/links",
        json={
            "process_id": processes["L3-032"]["id"],
            "kpi_id": kpis["EFF-01"]["id"],
            "note": "端到端周期",
        },
    )
    assert link.status_code == 201, link.text
    assert link.json()["kpi_code"] == "EFF-01"

    duplicate = client.post(
        f"{API}/strategy/objectives/{oid}/links",
        json={"process_id": processes["L3-032"]["id"], "kpi_id": kpis["EFF-01"]["id"]},
    )
    assert duplicate.status_code == 400
    assert "已存在" in duplicate.json()["detail"]

    # 创建不属于当前流程的临时 KPI，验证跨流程承接被拒绝。
    foreign_process = client.post(
        f"{API}/process-map",
        json={"code": "L3-STR-FOREIGN", "name": "战略测试外部流程", "level": 3},
    )
    assert foreign_process.status_code == 201, foreign_process.text
    foreign_process_id = foreign_process.json()["id"]
    foreign_kpi = client.post(
        f"{API}/monitor/kpis",
        json={
            "code": "STR-FOREIGN-" + uuid.uuid4().hex[:6],
            "name": "战略外部 KPI",
            "dimension": "EFFICIENCY",
            "kind": "PROCESS",
            "direction": "LOWER_BETTER",
            "unit": "天",
            "process_id": foreign_process_id,
            "formula": "A / B",
            "frequency": "MONTHLY",
            "red_threshold": 10,
            "yellow_threshold": 8,
            "green_threshold": 5,
        },
    )
    assert foreign_kpi.status_code == 201, foreign_kpi.text
    mismatch = client.post(
        f"{API}/strategy/objectives/{oid}/links",
        json={"process_id": processes["L3-032"]["id"], "kpi_id": foreign_kpi.json()["id"]},
    )
    assert mismatch.status_code == 400
    assert "不属于" in mismatch.json()["detail"]
    client.delete(f"{API}/monitor/kpis/{foreign_kpi.json()['id']}")
    client.delete(f"{API}/process-map/{foreign_process_id}")

    assert (
        client.delete(f"{API}/strategy/objectives/{oid}/links/{link.json()['id']}").status_code
        == 200
    )
    again = client.delete(f"{API}/strategy/objectives/{oid}/links/{link.json()['id']}")
    assert again.status_code == 404

    client.delete(f"{API}/strategy/objectives/{oid}")


def test_meta_and_permissions(client, viewer_client):
    meta = client.get(f"{API}/strategy/meta").json()
    assert meta["period_labels"]["ANNUAL"] == "年度"
    assert meta["status_labels"]["ACTIVE"] == "进行中"

    r = viewer_client.post(f"{API}/strategy/objectives", json=_objective_payload())
    assert r.status_code == 403
