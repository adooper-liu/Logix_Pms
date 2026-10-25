"""工作量预测与派工均衡。"""

from __future__ import annotations

API = "/api/v1"


def test_workload_forecast_and_balance(client, viewer_client):
    forecast = client.get(f"{API}/workforce/forecast", params={"months": 3, "growth_pct": 10})
    assert forecast.status_code == 200, forecast.text
    body = forecast.json()
    assert body["months"] == 3
    assert body["growth_pct"] == 10
    assert isinstance(body["rows"], list)
    assert body["total_available_minutes"] >= 0

    balance = client.get(f"{API}/workforce/balance")
    assert balance.status_code == 200, balance.text
    payload = balance.json()
    assert payload["deficit_positions"] >= 0
    assert isinstance(payload["suggestions"], list)

    assert viewer_client.get(f"{API}/workforce/balance").status_code == 403


def test_process_mining_returns_variants(client):
    rows = client.get(f"{API}/process-map/flat").json()
    process_id = next(row["id"] for row in rows if row["code"] == "L3-032")
    result = client.get(f"{API}/execution/mining", params={"process_id": process_id, "limit": 10})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["process_id"] == process_id
    assert body["instance_total"] >= 0
    assert isinstance(body["variants"], list)
    for row in body["variants"]:
        assert row["node_keys"]
        assert 0 <= row["share_pct"] <= 100
