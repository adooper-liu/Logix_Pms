"""九步启动状态：readiness 由现有数据自动计算。"""

from __future__ import annotations

API = "/api/v1"


def test_startup_status_shape(client):
    data = client.get(f"{API}/start/status").json()
    assert data["total"] == 9
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
    for step in data["steps"]:
        assert step["status"] in {"NOT_STARTED", "IN_PROGRESS", "READY"}
        assert step["status_label"] in {"未开始", "进行中", "已就绪"}
        assert step["title"] and step["goal"] and step["input"] and step["output"]
        assert isinstance(step["evidence"], dict)
        assert step["actions"]

    by_key = {step["key"]: step for step in data["steps"]}
    assert by_key["scope"]["status"] == "READY"
    assert by_key["strategy"]["status"] == "READY"
    assert by_key["architecture"]["status"] == "READY"
    assert by_key["workload"]["status"] == "READY"
    assert by_key["performance"]["status"] == "READY"
    # 种子数据还没有 KPI 越线改善项目与已应用变更单
    assert by_key["improvement"]["status"] != "READY"
    assert data["next_step"] is not None


def test_startup_status_for_owner(owner_client):
    data = owner_client.get(f"{API}/start/status").json()
    assert data["total"] == 9
    assert data["steps"]
