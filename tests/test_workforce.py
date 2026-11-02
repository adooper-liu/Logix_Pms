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
    design = client.get(f"{API}/processes/{process_id}/design").json()
    names = [node["name"] for node in design["nodes"] if node["node_type"] not in ("START", "END")][
        :2
    ]
    assert len(names) == 2
    before = client.get(
        f"{API}/execution/mining", params={"process_id": process_id, "limit": 100}
    ).json()
    for index, activity in enumerate(names):
        saved = client.post(
            f"{API}/pilot/event-logs",
            json={
                "process_id": process_id,
                "source_name": "手记",
                "case_key": "MINING-ALIGN",
                "activity_name": activity,
                "occurred_at": f"2026-11-01T08:0{index}:00",
            },
        )
        assert saved.status_code == 200, saved.text
    raw = client.post(
        f"{API}/pilot/event-logs",
        json={
            "process_id": process_id,
            "source_name": "手记",
            "case_key": "MINING-RAW",
            "activity_name": "手记未对上的活动",
            "occurred_at": "2026-11-01T09:00:00",
        },
    )
    assert raw.status_code == 200, raw.text
    started = client.post(
        f"{API}/execution/instances",
        json={"process_id": process_id, "variables": {"case": "mining-open"}},
    )
    assert started.status_code == 201, started.text
    result = client.get(f"{API}/execution/mining", params={"process_id": process_id, "limit": 100})
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["process_id"] == process_id
    assert body["instance_total"] == before["instance_total"] + 2
    assert body["unsequenced_instances"] == before["unsequenced_instances"] + 1
    assert sum(row["instance_count"] for row in body["variants"]) == body["instance_total"]
    assert isinstance(body["handoffs"], list)
    aligned = next(row for row in body["variants"] if row["node_names"] == names)
    assert aligned["source_label"] in ("手记日志", "实例和手记日志")
    assert aligned["instance_count"] >= 1
    assert all(not key.startswith("log:") for key in aligned["node_keys"])
    raw_row = next(row for row in body["variants"] if row["node_names"] == ["手记未对上的活动"])
    assert raw_row["source_label"] == "手记日志"
    assert raw_row["node_keys"] == ["log:手记未对上的活动"]
    for row in body["variants"]:
        assert row["node_keys"]
        assert row["source_label"] in ("实例", "手记日志", "实例和手记日志")
        assert 0 <= row["share_pct"] <= 100
    client.post(f"{API}/execution/instances/{started.json()['id']}/cancel")
