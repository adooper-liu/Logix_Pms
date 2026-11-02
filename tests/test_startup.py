"""开始使用：只数流程框架边界，由现有数据自动计算。"""

from __future__ import annotations

API = "/api/v1"


def _step(data: dict, key: str) -> dict:
    return next(step for step in data["steps"] if step["key"] == key)


def test_startup_status_shape(client):
    data = client.get(f"{API}/start/status").json()
    assert data["total"] == 1
    assert data["pilot_total"] == 0
    assert data["pilot_gate_open"] is False
    assert data["pilot_missing_steps"] == []
    assert len(data["steps"]) == 1
    assert data["steps"][0]["key"] == "framework"
    assert data["steps"][0]["pilot"] is False
    assert 0 <= data["readiness_pct"] <= 100

    step = data["steps"][0]
    assert step["status"] in {"NOT_STARTED", "IN_PROGRESS", "READY", "SKIPPED"}
    assert step["title"] and step["goal"] and step["input"] and step["output"]
    assert "端到端" not in step["goal"]
    assert "十层核对" not in step["goal"]
    from app.services.startup import STEP_DEFINITIONS

    defined = next(item for item in STEP_DEFINITIONS if item["key"] == "framework")
    assert "十层核对" in defined["next_hint"]
    assert step["next_hint"] is None
    assert [point["label"] for point in step["points"]] == ["生命周期", "地图", "改图的人"]
    keys = [item["key"] for item in step["evidence_items"]]
    assert keys == [
        "anchored_l3",
        "l1",
        "l2",
        "l3",
        "pcf_mapped_l3",
        "governance_roles",
    ]
    assert "process_charters" not in keys
    assert "boundary_gaps" not in keys
    assert "coverage_gaps" not in keys
    for item in step["evidence_items"]:
        assert item["required"] is True
        assert item["label"]
    missing = [item for item in step["evidence_items"] if not item["met"]]
    assert (step["status"] == "READY") == (not missing)
    # 种子地图和治理角色已经齐，框架边界按这两件判定
    assert step["status"] == "READY"
    assert data["next_step"] is None
    assert data["readiness_pct"] == 100


def test_startup_evidence_counts_the_map(client):
    data = client.get(f"{API}/start/status").json()
    items = {item["key"]: item for item in _step(data, "framework")["evidence_items"]}
    assert items["anchored_l3"]["value"] > 0
    assert items["anchored_l3"]["met"] is True
    assert items["pcf_mapped_l3"]["value"] > 0
    assert items["governance_roles"]["value"] > 0
    assert items["governance_roles"]["view"] == "orgs"
    assert items["l1"]["view"] == "map"


def test_every_evidence_count_opens_its_page(client):
    """每条计数都带落点页面，和证据定义是同一份。"""
    from app.services.startup import EVIDENCE_DESTINATIONS, EVIDENCE_ITEMS, EVIDENCE_LABELS

    assert set(EVIDENCE_DESTINATIONS) == set(EVIDENCE_LABELS)
    used = {item_key for items in EVIDENCE_ITEMS.values() for item_key, _required in items}
    assert used <= set(EVIDENCE_DESTINATIONS)
    allowed = {
        "map",
        "orgs",
        "projects",
        "strategy",
        "designer",
        "deliverables",
        "authorization",
        "execution",
        "monitor",
        "toolbox",
        "start",
        "pilot",
    }
    assert {view for view, _params in EVIDENCE_DESTINATIONS.values()} <= allowed

    data = client.get(f"{API}/start/status").json()
    framework = _step(data, "framework")
    for item in framework["evidence_items"]:
        view, params = EVIDENCE_DESTINATIONS[item["key"]]
        assert item["view"] == view
        assert item["view_params"] == params
    assert framework["actions"][0]["label"] == "去建流程地图"
    guided = next(a for a in framework["actions"] if a["label"] == "1+3+10 建架构")
    assert guided["action"] == "start.guidedPcf"
    appoint = next(a for a in framework["actions"] if a["label"] == "去任命治理角色")
    assert appoint["view"] == "orgs"
    assert appoint["view_params"] == {"tab": "governance"}
    assert all(a["action"] != "start.openBoundary" for a in framework["actions"])
    assert all(a["action"] != "start.openCoverage" for a in framework["actions"])
    assert "boundary_gaps" not in EVIDENCE_DESTINATIONS
    assert "coverage_gaps" not in EVIDENCE_DESTINATIONS
    assert EVIDENCE_DESTINATIONS["process_charters"] == ("pilot", {})
    assert EVIDENCE_DESTINATIONS["objective_complete"] == ("strategy", {})
    assert EVIDENCE_DESTINATIONS["rpa_runs"] == ("pilot", {})
    assert EVIDENCE_DESTINATIONS["process_cases"] == ("pilot", {})
    assert EVIDENCE_DESTINATIONS["technology_uses"] == ("pilot", {})
    assert EVIDENCE_DESTINATIONS["mining_variants"] == ("monitor", {"tab": "mining"})
    assert EVIDENCE_DESTINATIONS["rpa_bots"] == ("pilot", {})
    assert EVIDENCE_DESTINATIONS["training_records"] == ("pilot", {})


def test_startup_status_for_owner(owner_client):
    data = owner_client.get(f"{API}/start/status").json()
    assert data["total"] == 1
    assert data["steps"]


def test_skip_marks_unverified_and_unblocks_next(client):
    before = client.get(f"{API}/start/status").json()
    framework = _step(before, "framework")
    assert framework["status"] == "READY"
    ready_before = before["ready_count"]
    assert ready_before == 1

    try:
        skipped = client.post(f"{API}/start/steps/framework/skip", json={"reason": "样本复核中"})
        assert skipped.status_code == 200, skipped.text
        data = skipped.json()
        step = _step(data, "framework")
        assert step["status"] == "SKIPPED"
        assert step["status_label"] == "这次先不做（未验证）"
        assert step["skipped"] is True
        assert step["skip_reason"] == "样本复核中"
        assert step["skipped_by"] == "系统管理员"
        assert data["ready_count"] == 0
        assert data["skipped_count"] == 1
        assert data["next_step"] is None

        # 重复跳过是幂等的：更新原因，不新增记录
        again = client.post(f"{API}/start/steps/framework/skip", json={"reason": "等待新样本"})
        assert again.status_code == 200
        assert again.json()["skipped_count"] == 1
        assert _step(again.json(), "framework")["skip_reason"] == "等待新样本"
    finally:
        undone = client.delete(f"{API}/start/steps/framework/skip")
        assert undone.status_code == 200, undone.text

    restored = undone.json()
    step = _step(restored, "framework")
    assert step["status"] == "READY"
    assert step["skipped"] is False
    assert restored["skipped_count"] == 0
    assert restored["ready_count"] == ready_before


def test_unskip_is_idempotent(client):
    response = client.delete(f"{API}/start/steps/framework/skip")
    assert response.status_code == 200
    assert _step(response.json(), "framework")["skipped"] is False


def test_skip_unknown_step(client):
    assert client.post(f"{API}/start/steps/nope/skip", json={}).status_code == 404
    assert client.delete(f"{API}/start/steps/nope/skip").status_code == 404


def test_skip_requires_manager(owner_client, viewer_client):
    assert owner_client.post(f"{API}/start/steps/framework/skip", json={}).status_code == 403
    assert viewer_client.post(f"{API}/start/steps/framework/skip", json={}).status_code == 403
    assert viewer_client.delete(f"{API}/start/steps/framework/skip").status_code == 403


def test_pilot_confirm_stays_closed(client):
    """框架边界不再打开「前若干步齐了才能首次上线」。"""
    status = client.get(f"{API}/start/status").json()
    assert status["pilot_gate_open"] is False
    rejected = client.post(f"{API}/start/pilot/confirm", json={"note": "测试"})
    assert rejected.status_code == 409, rejected.text
    assert "首次上线条件未满足" in rejected.json()["detail"]


def test_pilot_confirm_requires_manager(owner_client, viewer_client):
    assert owner_client.post(f"{API}/start/pilot/confirm", json={}).status_code == 403
    assert viewer_client.post(f"{API}/start/pilot/confirm", json={}).status_code == 403
    assert viewer_client.delete(f"{API}/start/pilot/confirm").status_code == 403


def test_charter_completes_one_process_boundary(client, viewer_client):
    """范围说明记在十层核对上，不记在开始使用的框架边界上。"""
    options = client.get(f"{API}/start/charter-options")
    assert options.status_code == 200, options.text
    body = options.json()
    owned = next(row for row in body["processes"] if row["has_owner"])
    sponsor = body["users"][0]["id"]
    payload = {
        "process_id": owned["id"],
        "purpose": "把结果交给下游",
        "starts_at": "需求提交",
        "ends_at": "下游签收",
        "in_scope": "这条 L3 的主路径",
        "out_of_scope": "其他 L3",
        "stop_condition": "发起人书面停止",
        "sponsor_user_id": sponsor,
    }
    blank = {**payload, "purpose": "   "}
    assert client.post(f"{API}/start/charters", json=blank).status_code == 400
    assert viewer_client.post(f"{API}/start/charters", json=payload).status_code == 403

    saved = client.post(f"{API}/start/charters", json=payload)
    assert saved.status_code == 200, saved.text
    company_keys = {item["key"] for item in _step(saved.json(), "framework")["evidence_items"]}
    assert "process_charters" not in company_keys

    created = client.post(f"{API}/pilot/paths", json={"process_id": owned["id"]})
    if created.status_code == 201:
        path_id = created.json()["id"]
        detail = created.json()
    else:
        listed = client.get(f"{API}/pilot/paths").json()
        path_id = next(row["id"] for row in listed if row["process_id"] == owned["id"])
        detail = client.get(f"{API}/pilot/paths/{path_id}").json()
    try:
        layer2 = next(layer for layer in detail["layers"] if layer["layer_no"] == 2)
        assert layer2["title"] == "这条流程的起止"
        item = layer2["evidence_items"][0]
        assert item["key"] == "process_charters"
        assert "本流程" in item["label"]
        assert item["value"] >= 1
        assert item["met"] is True
    finally:
        if created.status_code == 201:
            client.delete(f"{API}/pilot/paths/{path_id}")
