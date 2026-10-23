"""岗位主数据与用户绑定。"""

from __future__ import annotations

API = "/api/v1"


def test_position_crud_and_user_binding(client):
    rows = client.get(f"{API}/positions").json()
    assert any(item["name"] == "采购计划员" for item in rows), rows

    orgs = client.get(f"{API}/org-units").json()
    org = next(item for item in orgs if item["name"] == "采购部")
    created = client.post(
        f"{API}/positions",
        json={"code": "POS-E2E", "name": "E2E岗位", "org_unit_id": org["id"]},
    )
    assert created.status_code == 201, created.text
    position = created.json()
    assert position["org_unit_name"] == "采购部"

    updated = client.patch(f"{API}/positions/{position['id']}", json={"name": "E2E岗位2"})
    assert updated.status_code == 200
    assert updated.json()["name"] == "E2E岗位2"

    users = client.get(f"{API}/auth/users").json()
    viewer = next(item for item in users if item["username"] == "viewer")
    bound = client.patch(f"{API}/auth/users/{viewer['id']}", json={"position_id": position["id"]})
    assert bound.status_code == 200, bound.text
    assert bound.json()["position_name"] == "E2E岗位2"

    cleared = client.patch(f"{API}/auth/users/{viewer['id']}", json={"position_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["position_name"] is None

    deleted = client.delete(f"{API}/positions/{position['id']}")
    assert deleted.status_code == 200


def test_position_delete_protected_when_referenced(client):
    rows = client.get(f"{API}/positions").json()
    used = next(item for item in rows if item["name"] == "采购计划员")
    response = client.delete(f"{API}/positions/{used['id']}")
    assert response.status_code == 409
    assert "引用" in response.json()["detail"]
