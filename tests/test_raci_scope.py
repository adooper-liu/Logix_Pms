"""P1 活动/节点RACI作用域；旧事项不自动猜成活动。"""

from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def scope_case(client):
    suffix = uuid4().hex[:8]
    process = client.post(
        f"{API}/process-map", json={"code": f"SCP-{suffix}", "name": "作用域测试", "level": 3}
    ).json()
    activities = []
    for code in ["A", "B"]:
        response = client.post(
            f"{API}/process-map",
            json={
                "code": f"SC{code}-{suffix}",
                "name": "同名活动",
                "level": 4,
                "parent_id": process["id"],
            },
        )
        assert response.status_code == 201, response.text
        activities.append(response.json())
    design = client.put(
        f"{API}/processes/{process['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": "nA",
                    "name": "活动A",
                    "node_type": "TASK",
                    "process_arch_id": activities[0]["id"],
                },
                {
                    "node_key": "nB",
                    "name": "活动B",
                    "node_type": "TASK",
                    "process_arch_id": activities[1]["id"],
                },
            ],
            "edges": [{"source_key": "nA", "target_key": "nB"}],
        },
    )
    assert design.status_code == 200, design.text
    roles = client.get(f"{API}/governance/roles?active_only=true").json()[:2]
    yield process, activities, roles
    for entry in client.get(f"{API}/governance/raci?process_id={process['id']}").json()["matters"]:
        for row in entry["entries"]:
            assert client.delete(f"{API}/governance/raci/{row['id']}").status_code == 200
    assert client.delete(f"{API}/process-map/{process['id']}").status_code == 200


def test_activity_scopes_with_same_matter_have_independent_a(scope_case, client):
    process, activities, roles = scope_case
    rows = []
    for activity, role in zip(activities, roles, strict=True):
        response = client.post(
            f"{API}/governance/raci",
            json={
                "process_id": process["id"],
                "matter": "活动责任",
                "activity_id": activity["id"],
                "role_id": role["id"],
                "raci": "A",
            },
        )
        assert response.status_code == 201, response.text
        row = response.json()
        assert row["scope_key"] == f"ACTIVITY:{activity['id']}"
        assert row["activity_id"] == activity["id"]
        rows.append(row)
    assert rows[0]["id"] != rows[1]["id"]
    matrix = client.get(f"{API}/governance/raci?process_id={process['id']}").json()
    scoped = [m for m in matrix["matters"] if m["activity_id"] in {a["id"] for a in activities}]
    assert len(scoped) == 2
    assert all(m["has_accountable"] for m in scoped)
    assert {m["scope_key"] for m in scoped} == {r["scope_key"] for r in rows}


def test_scope_unique_a_and_old_matter_compatibility(scope_case, client):
    process, activities, roles = scope_case
    payload = {
        "process_id": process["id"],
        "matter": "活动责任",
        "activity_id": activities[0]["id"],
        "node_key": "nA",
        "role_id": roles[0]["id"],
        "raci": "A",
    }
    saved = client.post(f"{API}/governance/raci", json=payload)
    assert saved.status_code == 201, saved.text
    repeated = client.post(f"{API}/governance/raci", json=payload)
    assert repeated.status_code == 201
    assert repeated.json()["id"] == saved.json()["id"]
    conflict = client.post(f"{API}/governance/raci", json={**payload, "role_id": roles[1]["id"]})
    assert conflict.status_code == 400, conflict.text
    assert "已有 A" in conflict.json()["detail"]
    # 事项恰好同名仍属独立MATTER，不猜映射；旧客户端行为保留。
    old = client.post(
        f"{API}/governance/raci",
        json={
            "process_id": process["id"],
            "matter": "活动责任",
            "role_id": roles[1]["id"],
            "raci": "A",
        },
    )
    assert old.status_code == 201, old.text
    assert old.json()["scope_key"] == "MATTER:活动责任"
    assert old.json()["activity_id"] is None


def test_node_scope_rejects_unknown_or_wrong_activity(scope_case, client, viewer_client):
    process, activities, roles = scope_case
    base = {
        "process_id": process["id"],
        "matter": "节点责任",
        "role_id": roles[0]["id"],
        "raci": "A",
    }
    assert (
        client.post(f"{API}/governance/raci", json={**base, "node_key": "not-here"}).status_code
        == 400
    )
    assert (
        client.post(
            f"{API}/governance/raci",
            json={**base, "activity_id": activities[1]["id"], "node_key": "nA"},
        ).status_code
        == 400
    )
    valid = client.post(f"{API}/governance/raci", json={**base, "node_key": "nA"})
    assert valid.status_code == 201, valid.text
    assert valid.json()["scope_key"] == "NODE:nA"
    assert (
        viewer_client.post(f"{API}/governance/raci", json={**base, "node_key": "nB"}).status_code
        == 403
    )


def test_foreign_activity_and_inactive_role_rejected(scope_case, client):
    process, activities, roles = scope_case
    base = {
        "process_id": process["id"],
        "matter": "活动责任",
        "role_id": roles[0]["id"],
        "raci": "A",
    }
    foreign = next(
        row
        for row in client.get(f"{API}/process-map/flat").json()
        if row["level"] == 4 and row["parent_id"] != process["id"]
    )
    assert (
        client.post(
            f"{API}/governance/raci", json={**base, "activity_id": foreign["id"]}
        ).status_code
        == 400
    )
    role = client.post(
        f"{API}/governance/roles", json={"name": "停用角色", "is_active": False}
    ).json()
    try:
        assert (
            client.post(
                f"{API}/governance/raci",
                json={**base, "role_id": role["id"], "activity_id": activities[0]["id"]},
            ).status_code
            == 400
        )
    finally:
        assert client.delete(f"{API}/governance/roles/{role['id']}").status_code == 200
