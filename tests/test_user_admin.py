"""组织与人员管理：用户归属组织、筛选、角色变更与管理员保护。"""

from __future__ import annotations

API = "/api/v1"


def _orgs(client) -> dict:
    return {row["code"]: row for row in client.get(f"{API}/org-units").json()}


def test_auth_meta_and_user_org_management(client, viewer_client):
    meta = viewer_client.get(f"{API}/auth/meta").json()
    assert meta["role_labels"]["ADMIN"] == "系统管理员"
    assert any(role["value"] == "OWNER" for role in meta["roles"])

    # 普通用户不能管理人员
    assert viewer_client.get(f"{API}/auth/users").status_code == 403

    orgs = _orgs(client)
    east = orgs["CO-EAST"]

    r = client.post(
        f"{API}/auth/users",
        json={
            "username": "org_user",
            "display_name": "组织测试员",
            "password": "secret123",
            "role": "OWNER",
            "department": "采购部",
            "org_unit_id": east["id"],
        },
    )
    assert r.status_code == 201, r.text
    user = r.json()
    assert user["role_label"] == "流程 Owner"
    assert user["org_unit_name"] == "华东分公司"
    assert user["org_unit_id"] == east["id"]

    rows = client.get(f"{API}/auth/users", params={"org_unit_id": east["id"]}).json()
    assert any(row["username"] == "org_user" for row in rows)
    rows = client.get(f"{API}/auth/users", params={"role": "OWNER"}).json()
    assert all(row["role"] == "OWNER" for row in rows)
    rows = client.get(f"{API}/auth/users", params={"keyword": "org_user"}).json()
    assert [row["username"] for row in rows] == ["org_user"]

    assert (
        client.post(
            f"{API}/auth/users",
            json={
                "username": "org_user",
                "display_name": "重复",
                "password": "secret123",
                "role": "VIEWER",
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"{API}/auth/users",
            json={
                "username": "bad_org_user",
                "display_name": "无效组织",
                "password": "secret123",
                "role": "VIEWER",
                "org_unit_id": 999999,
            },
        ).status_code
        == 400
    )

    r = client.patch(
        f"{API}/auth/users/{user['id']}",
        json={
            "display_name": "组织测试员（改名）",
            "role": "VIEWER",
            "org_unit_id": None,
            "department": "观察员",
            "password": "newsecret123",
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["role_label"] == "只读"
    assert updated["org_unit_id"] is None
    assert updated["display_name"] == "组织测试员（改名）"

    # 新口令可登录
    login = client.post(
        f"{API}/auth/login",
        json={"username": "org_user", "password": "newsecret123"},
    )
    assert login.status_code == 200, login.text


def test_admin_cannot_demote_or_deactivate_self(client):
    me = client.get(f"{API}/auth/me").json()
    r = client.patch(f"{API}/auth/users/{me['id']}", json={"is_active": False})
    assert r.status_code == 400
    assert "当前登录" in r.json()["detail"]
    r = client.patch(f"{API}/auth/users/{me['id']}", json={"role": "VIEWER"})
    assert r.status_code == 400
    assert "当前登录" in r.json()["detail"]
