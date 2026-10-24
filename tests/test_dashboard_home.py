"""角色化工作台：不同角色看到不同的首屏待办。"""

from __future__ import annotations

API = "/api/v1"


def test_admin_home_has_setup_and_governance(client):
    data = client.get(f"{API}/dashboard/home").json()
    assert data["role"] == "ADMIN"
    assert data["role_label"] == "系统管理员"
    assert data["headline"]
    keys = {block["key"] for block in data["blocks"]}
    assert {"setup", "governance", "execution"} <= keys
    setup = next(block for block in data["blocks"] if block["key"] == "setup")
    assert any(action["view"] == "start" for action in setup["actions"])


def test_owner_home_is_personal(owner_client):
    data = owner_client.get(f"{API}/dashboard/home").json()
    assert data["role"] == "OWNER"
    assert data["display_name"] == "陈经理"
    keys = {block["key"] for block in data["blocks"]}
    assert {"my_processes", "my_kpi", "my_projects"} <= keys
    kpi = next(block for block in data["blocks"] if block["key"] == "my_kpi")
    labels = {item["label"] for item in kpi["items"]}
    assert {"指标总数", "红/黄", "待处理异常"} <= labels
    assert all(
        action["view"] in {"map", "monitor", "projects"}
        for block in data["blocks"]
        for action in block["actions"]
    )


def test_viewer_home_is_readonly(viewer_client):
    data = viewer_client.get(f"{API}/dashboard/home").json()
    assert data["role"] == "VIEWER"
    assert [block["key"] for block in data["blocks"]] == ["readonly"]
    assert data["headline"]
