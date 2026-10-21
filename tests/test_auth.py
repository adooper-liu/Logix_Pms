"""认证与授权的回归测试。"""

from __future__ import annotations

API = "/api/v1"


# ------------------------------------------------------------------ 登录


def test_login_returns_token_and_user(anon_client):
    r = anon_client.post(f"{API}/auth/login", json={"username": "admin", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert data["token"]
    assert data["expires_at"] > 0
    assert data["user"]["username"] == "admin"
    assert data["user"]["role"] == "ADMIN"
    assert "password_hash" not in data["user"]


def test_login_rejects_wrong_password(anon_client):
    r = anon_client.post(f"{API}/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401
    # 不区分「用户不存在」和「口令错误」，避免枚举账号
    r2 = anon_client.post(f"{API}/auth/login", json={"username": "nobody", "password": "x"})
    assert r2.status_code == 401
    assert r.json()["detail"] == r2.json()["detail"]


def test_anonymous_cannot_read_business_data(anon_client):
    for path in (
        "/projects",
        "/process-map/tree",
        "/dashboard/overview",
        "/monitor/kpi-radar",
        "/knowledge",
        "/tools/grouped",
    ):
        r = anon_client.get(API + path)
        assert r.status_code == 401, f"{path} 未鉴权"


def test_invalid_token_rejected(anon_client):
    r = anon_client.get(f"{API}/projects", headers={"Authorization": "Bearer not-a-real-token"})
    assert r.status_code == 401


def test_me_returns_profile(client):
    r = client.get(f"{API}/auth/me")
    assert r.status_code == 200
    assert r.json()["username"] == "admin"


# ------------------------------------------------------------------ 写权限


def test_viewer_is_read_only(viewer_client):
    assert viewer_client.get(f"{API}/projects").status_code == 200

    r = viewer_client.post(
        f"{API}/projects",
        json={"name": "只读用户不该建成", "methodology": "BPI", "owner": "某人"},
    )
    assert r.status_code == 403

    r = viewer_client.post(f"{API}/monitor/exceptions", json={"title": "只读用户不该登记"})
    assert r.status_code == 403


def test_manager_can_write(manager_client):
    created = manager_client.post(
        f"{API}/monitor/exceptions",
        json={"title": "流程管理科登记的异常", "severity": "LOW"},
    )
    assert created.status_code == 201, created.text
    assert (
        manager_client.delete(f"{API}/monitor/exceptions/{created.json()['id']}").status_code == 200
    )


def test_manager_cannot_manage_users(manager_client):
    r = manager_client.get(f"{API}/auth/users")
    assert r.status_code == 403


def test_owner_can_edit_own_project(owner_client):
    projects = owner_client.get(f"{API}/projects", params={"page_size": 100}).json()["items"]
    mine = next(p for p in projects if p["owner"] == "陈经理")
    r = owner_client.patch(f"{API}/projects/{mine['id']}", json={"priority": 2})
    assert r.status_code == 200, r.text
    assert r.json()["priority"] == 2


def test_owner_cannot_edit_someone_elses_project(owner_client):
    projects = owner_client.get(f"{API}/projects", params={"page_size": 100}).json()["items"]
    others = next(p for p in projects if p["owner"] != "陈经理")
    r = owner_client.patch(f"{API}/projects/{others['id']}", json={"priority": 4})
    assert r.status_code == 403
    assert "只能修改自己名下" in r.json()["detail"]


def test_owner_cannot_restructure_process_arch(owner_client):
    """流程架构属于结构性数据，只有管理科及以上能改。"""
    r = owner_client.post(
        f"{API}/process-map",
        json={"code": "L3-OWNER", "name": "Owner 不该能建", "level": 3},
    )
    assert r.status_code == 403


def test_owner_created_project_is_bound_to_self(owner_client):
    created = owner_client.post(
        f"{API}/projects",
        json={"name": "Owner 自建项目", "methodology": "BPI", "owner": "冒名顶替"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["owner"] == "陈经理", "Owner 立项必须挂在自己名下"


# ------------------------------------------------------------------ 用户管理


def test_admin_manages_users(client):
    created = client.post(
        f"{API}/auth/users",
        json={
            "username": "temp_user",
            "display_name": "临时用户",
            "password": "temp123456",
            "role": "VIEWER",
        },
    )
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    # 新用户可以登录，但只能读
    login = client.post(
        f"{API}/auth/login", json={"username": "temp_user", "password": "temp123456"}
    )
    assert login.status_code == 200
    headers = {"Authorization": "Bearer " + login.json()["token"]}
    assert client.get(f"{API}/projects", headers=headers).status_code == 200

    # 停用后立刻失效
    assert client.patch(f"{API}/auth/users/{uid}", json={"is_active": False}).status_code == 200
    blocked = client.post(
        f"{API}/auth/login", json={"username": "temp_user", "password": "temp123456"}
    )
    assert blocked.status_code == 403


def test_duplicate_username_rejected(client):
    r = client.post(
        f"{API}/auth/users",
        json={"username": "admin", "display_name": "重名", "password": "whatever123"},
    )
    assert r.status_code == 409


def test_change_own_password(client):
    created = client.post(
        f"{API}/auth/users",
        json={
            "username": "pwd_user",
            "display_name": "改密用户",
            "password": "old123456",
            "role": "VIEWER",
        },
    )
    assert created.status_code == 201
    login = client.post(f"{API}/auth/login", json={"username": "pwd_user", "password": "old123456"})
    headers = {"Authorization": "Bearer " + login.json()["token"]}

    r = client.post(
        f"{API}/auth/change-password",
        headers=headers,
        json={"old_password": "old123456", "new_password": "new123456"},
    )
    assert r.status_code == 200
    assert (
        client.post(
            f"{API}/auth/login", json={"username": "pwd_user", "password": "old123456"}
        ).status_code
        == 401
    )
    assert (
        client.post(
            f"{API}/auth/login", json={"username": "pwd_user", "password": "new123456"}
        ).status_code
        == 200
    )


# ------------------------------------------------------------------ 审计留痕


def test_writes_are_audited(client):
    created = client.post(
        f"{API}/monitor/exceptions",
        json={"title": "审计探测", "severity": "LOW"},
    ).json()
    client.patch(f"{API}/monitor/exceptions/{created['id']}", json={"status": "IN_PROGRESS"})
    client.delete(f"{API}/monitor/exceptions/{created['id']}")

    logs = client.get(f"{API}/audit", params={"entity_type": "exception", "limit": 200}).json()
    assert logs["total"] >= 3
    mine = [i for i in logs["items"] if i["entity_id"] == created["id"]]
    actions = {i["action"] for i in mine}
    assert {"CREATE", "UPDATE", "DELETE"} <= actions
    assert all(i["username"] for i in mine)


def test_audit_records_actor(client):
    projects = client.get(f"{API}/projects", params={"page_size": 1}).json()["items"]
    pid = projects[0]["id"]
    client.patch(f"{API}/projects/{pid}", json={"progress": 42})

    logs = client.get(f"{API}/audit", params={"entity_type": "project", "limit": 50}).json()
    latest = logs["items"][0]
    assert latest["username"] == "admin"
    assert latest["display_name"] == "系统管理员"


def test_viewer_cannot_read_audit(viewer_client):
    assert viewer_client.get(f"{API}/audit").status_code == 403
