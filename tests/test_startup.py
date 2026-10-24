"""九步启动状态：readiness 由现有数据自动计算。"""

from __future__ import annotations

API = "/api/v1"

PILOT_KEYS = {
    "scope",
    "strategy",
    "architecture",
    "org_raci",
    "policy",
    "process_design",
    "workload",
    "performance",
}


def _step(data: dict, key: str) -> dict:
    return next(step for step in data["steps"] if step["key"] == key)


def test_startup_status_shape(client):
    data = client.get(f"{API}/start/status").json()
    assert data["total"] == 9
    assert data["pilot_total"] == 8
    assert len(data["steps"]) == 9
    assert [step["key"] for step in data["steps"]] == [
        "scope",
        "strategy",
        "architecture",
        "org_raci",
        "policy",
        "process_design",
        "workload",
        "performance",
        "improvement",
    ]
    assert 0 <= data["readiness_pct"] <= 100
    assert 0 <= data["pilot_readiness_pct"] <= 100
    assert {step["key"] for step in data["steps"] if step["pilot"]} == PILOT_KEYS
    assert _step(data, "improvement")["pilot"] is False
    if data["next_pilot_step"] is not None:
        assert data["next_pilot_step"] in PILOT_KEYS

    for step in data["steps"]:
        assert step["status"] in {"NOT_STARTED", "IN_PROGRESS", "READY", "SKIPPED"}
        assert step["status_label"] in {"未开始", "进行中", "已就绪", "未验证（已跳过）"}
        assert step["title"] and step["goal"] and step["input"] and step["output"]
        assert step["estimated"]
        assert isinstance(step["evidence"], dict)
        assert step["actions"]
        assert step["evidence_items"], f"{step['key']} 缺少结构化证据"
        for item in step["evidence_items"]:
            assert {"key", "label", "value", "required", "met"} <= set(item)
            assert item["label"]
            assert isinstance(item["required"], bool)
            assert isinstance(item["met"], bool)
        missing = [item for item in step["evidence_items"] if item["required"] and not item["met"]]
        assert (step["status"] == "READY") == (not missing)

    by_key = {step["key"]: step for step in data["steps"]}
    assert by_key["scope"]["status"] == "READY"
    assert by_key["strategy"]["status"] == "READY"
    assert by_key["architecture"]["status"] == "READY"
    assert by_key["workload"]["status"] == "READY"
    assert by_key["performance"]["status"] == "READY"
    # 种子数据还没有 KPI 越线改善项目与已应用变更单
    assert by_key["improvement"]["status"] != "READY"
    assert data["next_step"] is not None


def test_startup_evidence_zero_is_good(client):
    data = client.get(f"{API}/start/status").json()
    raci = _step(data, "org_raci")
    invalid = next(item for item in raci["evidence_items"] if item["key"] == "invalid_processes")
    assert invalid["value"] == 0
    assert invalid["met"] is True

    architecture = _step(data, "architecture")
    mapped = next(item for item in architecture["evidence_items"] if item["key"] == "pcf_mapped_l3")
    assert mapped["value"] > 0
    assert mapped["met"] is True


def test_startup_status_for_owner(owner_client):
    data = owner_client.get(f"{API}/start/status").json()
    assert data["total"] == 9
    assert data["steps"]


def test_skip_marks_unverified_and_unblocks_next(client):
    before = client.get(f"{API}/start/status").json()
    workload = _step(before, "workload")
    assert workload["status"] == "READY"
    ready_before = before["ready_count"]

    try:
        skipped = client.post(f"{API}/start/steps/workload/skip", json={"reason": "样本复核中"})
        assert skipped.status_code == 200, skipped.text
        data = skipped.json()
        step = _step(data, "workload")
        assert step["status"] == "SKIPPED"
        assert step["status_label"] == "未验证（已跳过）"
        assert step["skipped"] is True
        assert step["skip_reason"] == "样本复核中"
        assert step["skipped_by"] == "系统管理员"
        assert data["ready_count"] == ready_before - 1
        assert data["skipped_count"] == 1
        assert data["next_step"] != "workload"

        # 重复跳过是幂等的：更新原因，不新增记录
        again = client.post(f"{API}/start/steps/workload/skip", json={"reason": "等待新样本"})
        assert again.status_code == 200
        assert again.json()["skipped_count"] == 1
        assert _step(again.json(), "workload")["skip_reason"] == "等待新样本"
    finally:
        undone = client.delete(f"{API}/start/steps/workload/skip")
        assert undone.status_code == 200, undone.text

    restored = undone.json()
    step = _step(restored, "workload")
    assert step["status"] == "READY"
    assert step["skipped"] is False
    assert restored["skipped_count"] == 0
    assert restored["ready_count"] == ready_before


def test_unskip_is_idempotent(client):
    response = client.delete(f"{API}/start/steps/policy/skip")
    assert response.status_code == 200
    assert _step(response.json(), "policy")["skipped"] is False


def test_skip_unknown_step(client):
    assert client.post(f"{API}/start/steps/nope/skip", json={}).status_code == 404
    assert client.delete(f"{API}/start/steps/nope/skip").status_code == 404


def test_skip_requires_manager(owner_client, viewer_client):
    assert owner_client.post(f"{API}/start/steps/policy/skip", json={}).status_code == 403
    assert viewer_client.post(f"{API}/start/steps/policy/skip", json={}).status_code == 403
    assert viewer_client.delete(f"{API}/start/steps/policy/skip").status_code == 403
