"""流程卡：一条流程的跨模块聚合。"""

from __future__ import annotations

API = "/api/v1"


def _process(client, code: str) -> dict:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)


def test_process_card_for_l3(client):
    process = _process(client, "L3-032")
    card = client.get(f"{API}/process-card/{process['id']}").json()
    assert card["process"]["code"] == "L3-032"
    assert card["process"]["level"] == 3
    assert card["chain"][-1]["code"] == "L3-032"
    assert len(card["chain"]) >= 3

    assert "OBJ-2026-01" in {row["code"] for row in card["objectives"]}
    assert len(card["raci"]) >= 4
    assert all(matter["has_accountable"] for matter in card["raci"])

    assert card["model"]["node_count"] >= 5
    assert card["model"]["form_count"] >= 1
    assert card["workload"]["verified_standards"] >= 1
    assert card["workload"]["demand_hours"] > 0

    kpi_codes = {row["code"] for row in card["kpis"]}
    assert {"EFF-01", "EFF-04", "CST-01", "HLT-01"} <= kpi_codes
    assert all(row["status"] in {"RED", "YELLOW", "GREEN", "GRAY"} for row in card["kpis"])

    assert set(card["readiness"]) == {
        "strategy",
        "raci",
        "policy",
        "model",
        "workload",
        "kpi",
        "improvement",
        "governance",
    }
    assert card["readiness"]["strategy"] is True
    assert card["readiness"]["raci"] is True
    assert card["readiness"]["kpi"] is True


def test_process_card_for_l4(client):
    process = _process(client, "L4-202")
    card = client.get(f"{API}/process-card/{process['id']}").json()
    assert card["process"]["level"] == 4
    assert card["chain"][-1]["code"] == "L4-202"
    assert card["workload"]["verified_standards"] >= 1


def test_process_card_missing(client):
    assert client.get(f"{API}/process-card/999999").status_code == 404
