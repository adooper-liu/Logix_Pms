"""变更治理：影响分析门禁、审批状态机与模型发布联动。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process(client, code: str) -> dict:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row for row in rows if row["code"] == code)


def _impact() -> dict:
    return {
        "people": "采购员、采购经理",
        "systems": "采购系统与 OA 审批流",
        "data": "供应商准入状态字段",
        "permissions": "未准入供应商不可创建询价单",
        "controls": "准入校验为不可跳过控制点",
        "training": "采购员培训 1 小时",
        "kpis": "询比价周期观察 2 个月",
    }


def _payload(process_id: int, **overrides) -> dict:
    payload = {
        "process_id": process_id,
        "title": "变更测试-" + uuid.uuid4().hex[:6],
        "reason": "审计发现控制缺口",
        "scope": "测试范围",
        "change_type": "STRUCTURE",
        "impact_level": "MAJOR",
        "version_label": "V2.0",
        "impact": _impact(),
        "test_evidence": "测试环境回归通过",
        "rollback_plan": "关闭开关并恢复旧版本",
    }
    payload.update(overrides)
    return payload


def _approved(client, process_id: int, **overrides) -> dict:
    created = client.post(f"{API}/changes", json=_payload(process_id, **overrides))
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert client.post(f"{API}/changes/{cid}/submit").status_code == 200
    approved = client.post(f"{API}/changes/{cid}/approve", json={"note": "同意"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    return approved.json()


def _save_design(client, process_id: int) -> dict:
    response = client.put(
        f"{API}/processes/{process_id}/design",
        json={
            "nodes": [
                {
                    "node_key": "a",
                    "name": "变更测试活动",
                    "node_type": "TASK",
                    "lane": "L",
                    "duration_minutes": 10,
                }
            ],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_seeded_change_and_gate_flag(client):
    gated = _process(client, "L3-033")
    assert gated["requires_change_request"] is True
    normal = _process(client, "L3-032")
    assert normal["requires_change_request"] is False

    rows = client.get(f"{API}/changes", params={"process_id": gated["id"]}).json()
    seeded = next(row for row in rows if row["code"] == "CR-2026-001")
    assert seeded["status"] == "DRAFT"
    assert seeded["impact_level_label"] == "重大"
    assert set(seeded["impact"]) >= {
        "people",
        "systems",
        "data",
        "permissions",
        "controls",
        "training",
        "kpis",
    }
    assert seeded["requested_by_name"] == "流程管理科"


def test_major_change_requires_full_impact(client):
    process_id = _process(client, "L3-033")["id"]
    created = client.post(f"{API}/changes", json=_payload(process_id, impact={})).json()
    rejected = client.post(f"{API}/changes/{created['id']}/submit")
    assert rejected.status_code == 400
    assert "影响分析" in rejected.json()["detail"]

    patched = client.patch(f"{API}/changes/{created['id']}", json={"impact": _impact()})
    assert patched.status_code == 200, patched.text
    submitted = client.post(f"{API}/changes/{created['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "SUBMITTED"

    approved = client.post(f"{API}/changes/{created['id']}/approve", json={"note": "通过"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["approved_by_name"] == "系统管理员"


def test_gate_blocks_publish_until_approved(client):
    # 用临时流程测试门禁，避免覆盖种子流程的已发布模型
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-CGATE", "name": "变更门禁测试", "level": 3},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    assert (
        client.patch(f"{API}/process-map/{pid}", json={"requires_change_request": True}).status_code
        == 200
    )
    _save_design(client, pid)

    blocked = client.post(f"{API}/processes/{pid}/design/publish", json={})
    assert blocked.status_code == 409
    assert "变更门禁" in blocked.json()["detail"]

    other = _process(client, "L3-032")["id"]
    other_change = _approved(client, other)
    wrong = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"change_request_id": other_change["id"]},
    )
    assert wrong.status_code == 409
    assert "不属于" in wrong.json()["detail"]

    change = _approved(client, pid)
    published = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"change_request_id": change["id"]},
    )
    assert published.status_code == 200, published.text
    version_id = published.json()["version_id"]
    version = client.get(f"{API}/processes/{pid}/design/versions/{version_id}").json()
    assert version["change_request_id"] == change["id"]

    applied = client.get(f"{API}/changes/{change['id']}").json()
    assert applied["status"] == "APPLIED"
    assert applied["applied_at"]
    assert applied["linked_versions"][0]["id"] == version_id

    client.delete(f"{API}/process-map/{pid}")


def test_reject_and_cancel(client):
    process_id = _process(client, "L3-033")["id"]
    created = client.post(f"{API}/changes", json=_payload(process_id, impact_level="MINOR")).json()
    assert client.post(f"{API}/changes/{created['id']}/submit").status_code == 200
    rejected = client.post(f"{API}/changes/{created['id']}/reject", json={"note": "影响分析不充分"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["decision_note"] == "影响分析不充分"

    draft = client.post(f"{API}/changes", json=_payload(process_id, impact_level="PATCH")).json()
    cancelled = client.post(f"{API}/changes/{draft['id']}/cancel")
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"

    not_submitted = client.post(f"{API}/changes/{draft['id']}/approve", json={})
    assert not_submitted.status_code == 400


def test_gate_flag_is_configurable(client):
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-GATE", "name": "门禁配置测试", "level": 3},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    try:
        patched = client.patch(f"{API}/process-map/{pid}", json={"requires_change_request": True})
        assert patched.status_code == 200, patched.text
        assert patched.json()["requires_change_request"] is True
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_meta_and_permissions(client, viewer_client):
    meta = client.get(f"{API}/changes/meta").json()
    assert meta["status_labels"]["SUBMITTED"] == "待审批"
    assert meta["impact_level_labels"]["MAJOR"] == "重大"
    assert set(meta["impact_keys"]) == {
        "people",
        "systems",
        "data",
        "permissions",
        "controls",
        "training",
        "kpis",
    }
    process_id = _process(client, "L3-033")["id"]
    r = viewer_client.post(f"{API}/changes", json=_payload(process_id))
    assert r.status_code == 403
