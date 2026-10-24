"""角色化工作台：不同角色看到不同的首屏待办。"""

from __future__ import annotations

API = "/api/v1"


def test_admin_home_has_setup_and_governance(client):
    data = client.get(f"{API}/dashboard/home").json()
    assert data["role"] == "ADMIN"
    assert data["role_label"] == "系统管理员"
    assert data["headline"]
    keys = {block["key"] for block in data["blocks"]}
    assert {"setup", "governance"} <= keys
    assert "execution" not in keys, "执行概览应已合并进「我的当前推进」"
    setup = next(block for block in data["blocks"] if block["key"] == "setup")
    assert any(action["view"] == "start" for action in setup["actions"])
    assert data["active_project_count"] >= 1
    assert data["setup_project_count"] >= 0


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
    assert len(data["next_actions"]) <= 3


def test_home_next_actions_are_real_projects(client, owner_client):
    admin = client.get(f"{API}/dashboard/home").json()
    actions = admin["next_actions"]
    assert actions, "驾驶舱缺少当前推进项目"
    assert len(actions) <= 3
    first = actions[0]
    assert first["project_id"] and first["code"] and first["stage_name"]
    assert first["current_stage"] >= 1
    assert "next_step_name" in first
    assert isinstance(first["open_exceptions"], int)
    assert admin["active_project_count"] >= len(actions)

    owner = owner_client.get(f"{API}/dashboard/home").json()
    assert owner["next_actions"], "流程 Owner 没有当前推进项目"
    assert all(item["owner"] == "陈经理" for item in owner["next_actions"])
    assert owner["active_project_count"] >= len(owner["next_actions"])
