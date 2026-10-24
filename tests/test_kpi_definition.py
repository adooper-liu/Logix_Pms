"""KPI 定义卡：口径完整性、阈值语义、活动绑定与定义版本。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _code(prefix: str = "KPI") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _payload(**overrides) -> dict:
    payload = {
        "code": _code(),
        "name": "测试指标-" + uuid.uuid4().hex[:8],
        "dimension": "EFFICIENCY",
        "kind": "PROCESS",
        "direction": "LOWER_BETTER",
        "unit": "天",
        "target_value": 5.0,
        "baseline_value": 10.0,
        "formula": "Σ耗时 ÷ 单数",
        "numerator": "耗时合计",
        "denominator": "单数",
        "granularity": "单 / 月",
        "frequency": "MONTHLY",
        "source_system": "测试系统",
        "quality_rule": "剔除撤销单",
        "red_threshold": 8.0,
        "yellow_threshold": 6.5,
        "green_threshold": 5.0,
        "valid_from": "2026-01-01",
    }
    payload.update(overrides)
    return payload


def test_seeded_kpis_have_definition_cards(client):
    kpis = client.get(f"{API}/monitor/kpis").json()
    # 其他用例会创建测试 KPI；这里只校验种子指标
    seeded = [
        kpi for kpi in kpis if kpi["code"].startswith(("EFF-", "QUA-", "CST-", "FLX-", "HLT-"))
    ]
    assert len(seeded) == 16
    for kpi in seeded:
        assert kpi["formula"], f"{kpi['code']} 缺少公式"
        assert kpi["kind"] in {"RESULT", "PROCESS", "HEALTH"}
        assert kpi["kind_label"]
        assert kpi["frequency"] and kpi["frequency_label"]
        assert kpi["version"] == 1
        assert kpi["source_system"] and kpi["granularity"] and kpi["quality_rule"]

    by_code = {kpi["code"]: kpi for kpi in seeded}
    # 越小越好：10 天 > 红线 7.6 → 红
    assert by_code["EFF-05"]["status"] == "RED"
    assert by_code["EFF-05"]["status_label"] == "红"
    # 越大越好：97.2 ≥ 绿线 97 → 绿
    assert by_code["QUA-02"]["status"] == "GREEN"
    # 健康度指标
    assert by_code["HLT-01"]["kind"] == "HEALTH"
    assert by_code["HLT-01"]["status"] == "GREEN"
    # 种子里的「陈经理」应绑定到账号，而不是只有展示名
    assert by_code["EFF-01"]["owner_user_id"] is not None


def test_meta_labels_are_backend_owned(client):
    meta = client.get(f"{API}/monitor/meta").json()
    assert meta["kind_labels"] == {"RESULT": "结果", "PROCESS": "过程", "HEALTH": "健康度"}
    assert meta["frequency_labels"]["MONTHLY"] == "每月"
    assert meta["status_labels"]["RED"] == "红"
    assert meta["dimension_labels"]["EFFICIENCY"] == "效率"


def test_create_and_update_bump_definition_version(client):
    created = client.post(f"{API}/monitor/kpis", json=_payload())
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["version"] == 1
    assert data["kind_label"] == "过程"
    assert data["frequency_label"] == "每月"
    assert data["status"] == "GRAY"  # 还没有数据点：灰色等待信号
    assert data["status_label"] == "灰（未取数）"

    updated = client.patch(
        f"{API}/monitor/kpis/{data['id']}",
        json={"target_value": 4.0, "green_threshold": 4.0},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version"] == 2
    assert updated.json()["target_value"] == 4.0
    assert updated.json()["green_threshold"] == 4.0

    # 追加数据点不代表口径变化，版本不应 +1
    record = client.post(
        f"{API}/monitor/kpis/{data['id']}/records",
        json={"period": "2026-10-01", "value": 4.5},
    )
    assert record.status_code == 201, record.text
    detail = client.get(f"{API}/monitor/kpis/{data['id']}").json()
    assert detail["version"] == 2
    assert detail["status"] == "YELLOW"  # 4.5 介于绿线 4 与红线 8 之间


def test_definition_requires_formula_or_ratio(client):
    r = client.post(
        f"{API}/monitor/kpis",
        json=_payload(formula=None, numerator=None, denominator=None),
    )
    assert r.status_code == 400
    assert "计算公式" in r.json()["detail"]


def test_thresholds_must_be_complete_and_ordered(client):
    partial = client.post(
        f"{API}/monitor/kpis",
        json=_payload(red_threshold=8.0, yellow_threshold=None, green_threshold=5.0),
    )
    assert partial.status_code == 400
    assert "同时填写" in partial.json()["detail"]

    # 越小越好：红线 4 < 黄线 6 < 绿线 8 是反的
    wrong = client.post(
        f"{API}/monitor/kpis",
        json=_payload(red_threshold=4.0, yellow_threshold=6.0, green_threshold=8.0),
    )
    assert wrong.status_code == 400
    assert "红线" in wrong.json()["detail"]


def test_same_name_cannot_have_two_formulas(client):
    name = "同名指标-" + uuid.uuid4().hex[:6]
    first = client.post(
        f"{API}/monitor/kpis",
        json=_payload(name=name, process_id=None, formula="A ÷ B"),
    )
    assert first.status_code == 201, first.text

    conflict = client.post(
        f"{API}/monitor/kpis",
        json=_payload(name=name, process_id=None, formula="C ÷ D"),
    )
    assert conflict.status_code == 400
    assert "同名 KPI" in conflict.json()["detail"]

    # 同一公式可以通过
    same = client.post(
        f"{API}/monitor/kpis",
        json=_payload(name=name, process_id=None, formula="A ÷ B"),
    )
    assert same.status_code == 201, same.text


def test_activity_binding_must_be_l4_in_process_subtree(client):
    rows = client.get(f"{API}/process-map/flat").json()
    l3 = next(row for row in rows if row["level"] == 3)
    l4 = next(row for row in rows if row["level"] == 4 and row["parent_id"] == l3["id"])
    other_l4 = next(row for row in rows if row["level"] == 4 and row["parent_id"] != l3["id"])

    ok = client.post(
        f"{API}/monitor/kpis",
        json=_payload(process_id=l3["id"], activity_id=l4["id"]),
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["activity_id"] == l4["id"]

    not_l4 = client.post(
        f"{API}/monitor/kpis",
        json=_payload(process_id=l3["id"], activity_id=l3["id"]),
    )
    assert not_l4.status_code == 400
    assert "L4" in not_l4.json()["detail"]

    outside = client.post(
        f"{API}/monitor/kpis",
        json=_payload(process_id=l3["id"], activity_id=other_l4["id"]),
    )
    assert outside.status_code == 400
    assert "不属于" in outside.json()["detail"]


def test_filter_by_kind_and_read_detail(client):
    rows = client.get(f"{API}/monitor/kpis", params={"kind": "HEALTH"}).json()
    assert rows
    assert all(row["kind"] == "HEALTH" for row in rows)

    detail = client.get(f"{API}/monitor/kpis/{rows[0]['id']}").json()
    assert detail["code"] == rows[0]["code"]
    assert detail["kind_label"] == "健康度"


def test_viewer_cannot_manage_definition_cards(viewer_client):
    r = viewer_client.post(f"{API}/monitor/kpis", json=_payload())
    assert r.status_code == 403
