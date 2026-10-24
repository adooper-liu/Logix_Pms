"""治理角色与 RACI：成员、唯一 A 校验与治理扫描联动。"""

from __future__ import annotations

import uuid

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/process-map/flat").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _roles(client) -> dict[str, dict]:
    return {row["code"]: row for row in client.get(f"{API}/governance/roles").json()}


def _role_payload(**overrides) -> dict:
    payload = {
        "name": "测试治理角色-" + uuid.uuid4().hex[:6],
        "role_type": "OTHER",
        "description": "测试用",
    }
    payload.update(overrides)
    return payload


def test_seeded_roles_and_raci(client):
    roles = _roles(client)
    assert {"GR-001", "GR-002", "GR-004", "GR-006", "GR-007"} <= set(roles)
    assert roles["GR-002"]["role_type_label"] == "集团端到端流程所有者"
    assert roles["GR-002"]["member_count"] == 1
    assert roles["GR-002"]["members"][0]["user_name"] == "陈经理"

    meta = client.get(f"{API}/governance/meta").json()
    assert meta["raci_labels"]["A"] == "A 唯一负责"
    assert meta["role_type_labels"]["COMMITTEE"] == "集团流程治理委员会"

    process_id = _process_id(client, "L3-032")
    matrix = client.get(f"{API}/governance/raci", params={"process_id": process_id}).json()
    assert matrix["valid"] is True, matrix["errors"]
    assert len(matrix["matters"]) == 4
    assert all(matter["has_accountable"] for matter in matrix["matters"])
    for matter in matrix["matters"]:
        accountable = [entry for entry in matter["entries"] if entry["raci"] == "A"]
        assert len(accountable) == 1

    small = client.get(
        f"{API}/governance/raci", params={"process_id": _process_id(client, "L3-033")}
    ).json()
    assert small["valid"] is True
    assert small["matters"][0]["matter"] == "供应商准入例外"


def test_role_members_and_delete_guard(client):
    created = client.post(f"{API}/governance/roles", json=_role_payload())
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["code"].startswith("GR-")

    user_id = client.get(f"{API}/execution/assignees").json()[0]["id"]
    member = client.post(
        f"{API}/governance/roles/{role['id']}/members",
        json={"user_id": user_id, "is_primary": True},
    )
    assert member.status_code == 201, member.text
    assert member.json()["is_primary"] is True

    duplicate = client.post(
        f"{API}/governance/roles/{role['id']}/members", json={"user_id": user_id}
    )
    assert duplicate.status_code == 400
    assert "已在角色中" in duplicate.json()["detail"]

    assert (
        client.delete(
            f"{API}/governance/roles/{role['id']}/members/{member.json()['id']}"
        ).status_code
        == 200
    )
    assert client.delete(f"{API}/governance/roles/{role['id']}").status_code == 200

    # 被 RACI 使用的角色不能删除
    used = _roles(client)["GR-004"]
    blocked = client.delete(f"{API}/governance/roles/{used['id']}")
    assert blocked.status_code == 409
    assert "RACI" in blocked.json()["detail"]


def test_single_accountable_guard(client):
    roles = _roles(client)
    process_id = _process_id(client, "L3-032")

    with_new_role = client.post(f"{API}/governance/roles", json=_role_payload())
    new_role = with_new_role.json()
    conflict = client.post(
        f"{API}/governance/raci",
        json={
            "process_id": process_id,
            "matter": "流程变更审批",
            "role_id": new_role["id"],
            "raci": "A",
        },
    )
    assert conflict.status_code == 400
    assert "已有 A" in conflict.json()["detail"]

    # 同一个角色改成 R 可以
    as_r = client.post(
        f"{API}/governance/raci",
        json={
            "process_id": process_id,
            "matter": "流程变更审批",
            "role_id": new_role["id"],
            "raci": "R",
        },
    )
    assert as_r.status_code == 201, as_r.text
    assert client.delete(f"{API}/governance/raci/{as_r.json()['id']}").status_code == 200
    assert client.delete(f"{API}/governance/roles/{roles['GR-005']['id']}").status_code == 409
    client.delete(f"{API}/governance/roles/{new_role['id']}")


def test_raci_invalid_triggers_governance_finding(client):
    created = client.post(
        f"{API}/process-map",
        json={"code": "L3-RACI", "name": "RACI 校验测试", "level": 3},
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    roles = _roles(client)
    try:
        # 只有 R、没有 A → 矩阵无效
        entry = client.post(
            f"{API}/governance/raci",
            json={
                "process_id": pid,
                "matter": "例外审批",
                "role_id": roles["GR-005"]["id"],
                "raci": "R",
            },
        )
        assert entry.status_code == 201, entry.text
        matrix = client.get(f"{API}/governance/raci", params={"process_id": pid}).json()
        assert matrix["valid"] is False
        assert "没有 A" in matrix["errors"][0]

        client.post(f"{API}/baselines/audit-scan")
        findings = client.get(f"{API}/baselines/findings", params={"type": "RACI_INVALID"}).json()
        row = next(item for item in findings if item["entity_id"] == pid)
        assert row["status"] == "OPEN"
        assert "没有 A" in row["detail"]

        # 补上唯一 A 后再扫描，待办自动关闭
        fixed = client.post(
            f"{API}/governance/raci",
            json={
                "process_id": pid,
                "matter": "例外审批",
                "role_id": roles["GR-002"]["id"],
                "raci": "A",
            },
        )
        assert fixed.status_code == 201, fixed.text
        client.post(f"{API}/baselines/audit-scan")
        findings = client.get(f"{API}/baselines/findings", params={"type": "RACI_INVALID"}).json()
        resolved = next(item for item in findings if item["entity_id"] == pid)
        assert resolved["status"] == "RESOLVED"
    finally:
        client.delete(f"{API}/process-map/{pid}")


def test_viewer_cannot_manage_governance(viewer_client):
    assert viewer_client.post(f"{API}/governance/roles", json=_role_payload()).status_code == 403
