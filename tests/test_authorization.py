"""分级授权矩阵：规则生命周期、例外审批与权限。"""

from __future__ import annotations

API = "/api/v1"


def _rule_payload(**overrides) -> dict:
    payload = {
        "title": "测试授权规则",
        "matter": "测试关键事项",
        "category": "B",
        "risk_level": "MEDIUM",
        "amount_limit": 100000,
        "impact_scope": "单元内跨部门",
        "reversibility": "可回退",
        "frequency": "中频",
        "approver_label": "测试审批人",
        "exception_path": "由单元负责人审批，例外按月汇总。",
        "evidence_required": "变更单、测试证据",
        "valid_from": "2026-11-01",
        "valid_to": "2027-10-31",
    }
    payload.update(overrides)
    return payload


def _first_effective_rule(client) -> dict:
    rules = client.get(f"{API}/authorization/rules", params={"status": "EFFECTIVE"}).json()
    assert rules
    return rules[0]


def test_rule_lifecycle(client):
    created = client.post(f"{API}/authorization/rules", json=_rule_payload())
    assert created.status_code == 201, created.text
    rule = created.json()
    assert rule["code"].startswith("AUTH-")
    assert rule["status"] == "DRAFT"
    assert rule["status_label"] == "草稿"
    assert rule["category_label"].startswith("B 类")

    activated = client.post(f"{API}/authorization/rules/{rule['id']}/activate")
    assert activated.status_code == 200, activated.text
    assert activated.json()["status"] == "EFFECTIVE"
    assert activated.json()["version"] == 1

    # 修改已生效规则 → 回到草稿并升版
    patched = client.patch(
        f"{API}/authorization/rules/{rule['id']}", json={"title": "测试规则（修订）"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["status"] == "DRAFT"
    assert patched.json()["version"] == 2

    assert client.post(f"{API}/authorization/rules/{rule['id']}/activate").status_code == 200
    retired = client.post(f"{API}/authorization/rules/{rule['id']}/retire")
    assert retired.status_code == 200
    assert retired.json()["status"] == "RETIRED"

    # 停用后不能再改，也不能删除
    assert (
        client.patch(f"{API}/authorization/rules/{rule['id']}", json={"title": "再改"}).status_code
        == 400
    )
    assert client.delete(f"{API}/authorization/rules/{rule['id']}").status_code == 400


def test_activate_requires_completeness(client):
    created = client.post(
        f"{API}/authorization/rules",
        json=_rule_payload(approver_label="", exception_path="", evidence_required=""),
    )
    assert created.status_code == 201
    response = client.post(f"{API}/authorization/rules/{created.json()['id']}/activate")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "审批角色" in detail and "例外路径" in detail and "审批证据" in detail


def test_delete_draft_rule(client):
    created = client.post(f"{API}/authorization/rules", json=_rule_payload())
    rule_id = created.json()["id"]
    assert client.delete(f"{API}/authorization/rules/{rule_id}").status_code == 200
    assert client.get(f"{API}/authorization/rules/{rule_id}").status_code == 404


def test_exception_flow(client):
    created = client.post(f"{API}/authorization/rules", json=_rule_payload())
    rule_id = created.json()["id"]
    assert client.post(f"{API}/authorization/rules/{rule_id}/activate").status_code == 200

    requested = client.post(
        f"{API}/authorization/exceptions",
        json={
            "rule_id": rule_id,
            "title": "测试例外",
            "reason": "试点窗口与系统割接重叠",
            "scope": "仅限试点流程",
            "expires_at": "2026-12-31T00:00:00",
        },
    )
    assert requested.status_code == 201, requested.text
    exception = requested.json()
    assert exception["code"].startswith("AEX-")
    assert exception["status"] == "REQUESTED"
    assert exception["rule_code"] == created.json()["code"]

    approved = client.post(
        f"{API}/authorization/exceptions/{exception['id']}/approve",
        json={"note": "同意，割接后关闭"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED"
    assert approved.json()["decided_by_name"] == "系统管理员"

    closed = client.post(
        f"{API}/authorization/exceptions/{exception['id']}/close", json={"note": None}
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED"
    assert (
        client.post(
            f"{API}/authorization/exceptions/{exception['id']}/close", json={"note": None}
        ).status_code
        == 400
    )


def test_reject_requires_note(client):
    rule = _first_effective_rule(client)
    requested = client.post(
        f"{API}/authorization/exceptions",
        json={"rule_id": rule["id"], "title": "待驳回例外", "reason": "测试"},
    )
    assert requested.status_code == 201
    exception_id = requested.json()["id"]
    rejected = client.post(
        f"{API}/authorization/exceptions/{exception_id}/reject", json={"note": ""}
    )
    assert rejected.status_code == 400
    assert "原因" in rejected.json()["detail"]


def test_permissions(owner_client, viewer_client):
    assert viewer_client.post(f"{API}/authorization/rules", json=_rule_payload()).status_code == 403
    assert owner_client.post(f"{API}/authorization/rules", json=_rule_payload()).status_code == 403

    rule = _first_effective_rule(owner_client)
    requested = owner_client.post(
        f"{API}/authorization/exceptions",
        json={"rule_id": rule["id"], "title": "Owner 申请例外", "reason": "测试"},
    )
    assert requested.status_code == 201, requested.text
    exception_id = requested.json()["id"]
    # OWNER 可以申请，但不能批准
    assert (
        owner_client.post(
            f"{API}/authorization/exceptions/{exception_id}/approve", json={"note": None}
        ).status_code
        == 403
    )
    assert (
        viewer_client.post(
            f"{API}/authorization/exceptions",
            json={"rule_id": rule["id"], "title": "只读申请", "reason": "测试"},
        ).status_code
        == 403
    )
