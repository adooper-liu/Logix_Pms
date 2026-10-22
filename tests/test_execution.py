"""流程执行：实例、任务队列、分支、权限与闭环。"""

from __future__ import annotations

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _start(client, code: str = "L3-032") -> dict:
    r = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client, code), "variables": {"case": "test"}},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _open_task(client, instance_id: int) -> dict:
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    assert tasks, f"实例 {instance_id} 没有待办任务"
    return tasks[0]


def _complete(client, task_id: int, **payload) -> dict:
    r = client.post(f"{API}/execution/tasks/{task_id}/complete", json=payload)
    return r


# ------------------------------------------------------------------ 基础


def test_executable_processes(client):
    rows = client.get(f"{API}/execution/processes").json()
    codes = {r["code"] for r in rows}
    assert {"L3-032", "L3-033"} <= codes
    by_code = {r["code"]: r for r in rows}
    assert by_code["L3-032"]["node_count"] == 6
    assert by_code["L3-033"]["node_count"] >= 5


def test_start_requires_login(anon_client):
    assert anon_client.get(f"{API}/execution/processes").status_code == 401
    assert anon_client.get(f"{API}/execution/tasks").status_code == 401
    assert (
        anon_client.get(f"{API}/execution/assignments", params={"process_id": 1}).status_code == 401
    )


def test_seeded_instances_and_queue(client):
    instances = client.get(f"{API}/execution/instances").json()
    assert len(instances) >= 2
    assert all(i["status"] in ("RUNNING", "COMPLETED") for i in instances)

    tasks = client.get(f"{API}/execution/tasks", params={"only_open": True}).json()
    assert len(tasks) >= 2
    assert any(t["assignee_name"] for t in tasks), "种子数据应有一条已指派任务"
    assert any(t["assignee_user_id"] is None for t in tasks), "种子数据应有一条公共队列任务"


# ------------------------------------------------------------------ 主流程


def test_start_complete_branch_and_finish(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        assert task["node_key"] == "n1"
        assert task["next_options"][0]["node_key"] == "n2"

        claimed = client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert claimed.status_code == 200
        assert claimed.json()["status"] == "CLAIMED"
        assert claimed.json()["assignee_user_id"] is not None

        # n1 有必填表单，n2/n3 没有表单；每步只有一条出边
        for step in range(3):
            task = _open_task(client, iid)
            data = {"applicant": "测试申请人", "amount": 12000} if step == 0 else None
            done = _complete(client, task["id"], form_data=data)
            assert done.status_code == 200, done.text

        # n4 是审批分支：不指定下一步应拒绝
        n4 = _open_task(client, iid)
        assert n4["node_key"] == "n4"
        assert {o["node_key"] for o in n4["next_options"]} == {"n5", "n6"}
        # 缺必填表单 → 拒绝
        missing = _complete(client, n4["id"])
        assert missing.status_code == 400
        assert "是否通过" in missing.json()["detail"]
        # 审批不通过没有匹配规则 → 多分支必须显式选择
        rejected = _complete(client, n4["id"], form_data={"approved": "否"})
        assert rejected.status_code == 400
        assert "多个分支" in rejected.json()["detail"]

        # 审批通过命中规则 → 自动进入 n5；n5 无出边 → 实例完成
        assert _complete(client, n4["id"], form_data={"approved": "是"}).status_code == 200
        n5 = _open_task(client, iid)
        assert n5["node_key"] == "n5"
        assert _complete(client, n5["id"], comment="完成").status_code == 200

        detail = client.get(f"{API}/execution/instances/{iid}").json()
        assert detail["instance"]["status"] == "COMPLETED"
        assert detail["instance"]["open_task_count"] == 0
        assert detail["instance"]["current_node_key"] is None
        assert [t["node_key"] for t in detail["tasks"]] == ["n1", "n2", "n3", "n4", "n5"]
        assert all(t["status"] == "COMPLETED" for t in detail["tasks"])
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


def test_branch_back_to_previous_step_creates_new_task(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        for step in range(3):
            task = _open_task(client, iid)
            data = {"applicant": "回退测试", "amount": 5000} if step == 0 else None
            assert _complete(client, task["id"], form_data=data).status_code == 200
        n4 = _open_task(client, iid)
        assert n4["node_key"] == "n4"
        assert (
            _complete(
                client, n4["id"], form_data={"approved": "否"}, next_node_key="n6"
            ).status_code
            == 200
        )

        n6 = _open_task(client, iid)
        assert n6["node_key"] == "n6"
        assert _complete(client, n6["id"]).status_code == 200

        # n6 → n2，产生新的 n2 任务
        again = _open_task(client, iid)
        assert again["node_key"] == "n2"
        assert again["id"] != n6["id"]
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


# ------------------------------------------------------------------ 权限与改派


def test_owner_can_claim_and_complete_unassigned_task(owner_client):
    instance = _start(owner_client)
    iid = instance["id"]
    try:
        task = _open_task(owner_client, iid)
        assert task["assignee_user_id"] is None
        done = _complete(
            owner_client,
            task["id"],
            form_data={"applicant": "陈经理", "amount": 8000, "by": "owner"},
        )
        assert done.status_code == 200
        assert done.json()["assignee_name"] == "陈经理"
    finally:
        owner_client.delete(f"{API}/execution/instances/{iid}")


def test_viewer_cannot_claim_or_complete(viewer_client):
    task = viewer_client.get(f"{API}/execution/tasks", params={"only_open": True}).json()[0]
    assert viewer_client.post(f"{API}/execution/tasks/{task['id']}/claim").status_code == 403
    assert (
        viewer_client.post(f"{API}/execution/tasks/{task['id']}/complete", json={}).status_code
        == 403
    )


def test_manager_can_reassign_task(manager_client, owner_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        chen_id = owner_client.get(f"{API}/auth/me").json()["id"]
        assigned = manager_client.patch(
            f"{API}/execution/tasks/{task['id']}/assignee",
            json={"assignee_user_id": chen_id},
        )
        assert assigned.status_code == 200
        assert assigned.json()["assignee_user_id"] == chen_id
        assert assigned.json()["status"] == "CLAIMED"

        # 管理员有管理权限，可以直接完成；n1 有必填表单
        assert (
            _complete(
                manager_client,
                task["id"],
                form_data={"applicant": "管理员", "amount": 100},
            ).status_code
            == 200
        )

        # 退回公共队列
        next_task = _open_task(manager_client, iid)
        cleared = manager_client.patch(
            f"{API}/execution/tasks/{next_task['id']}/assignee",
            json={"assignee_user_id": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["status"] == "PENDING"
        assert cleared.json()["assignee_user_id"] is None
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


# ------------------------------------------------------------------ 取消 / 删除 / 审计


def test_cancel_instance_cancels_open_tasks(manager_client):
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        cancelled = manager_client.post(f"{API}/execution/instances/{iid}/cancel")
        assert cancelled.status_code == 200
        assert cancelled.json()["status"] == "CANCELLED"
        assert cancelled.json()["open_task_count"] == 0

        # 已取消的实例不能再处理任务
        detail = manager_client.get(f"{API}/execution/instances/{iid}").json()
        assert all(t["status"] == "CANCELLED" for t in detail["tasks"])
        assert (
            manager_client.post(
                f"{API}/execution/tasks/{detail['tasks'][0]['id']}/complete", json={}
            ).status_code
            == 409
        )
        assert manager_client.post(f"{API}/execution/instances/{iid}/cancel").status_code == 409
    finally:
        assert manager_client.delete(f"{API}/execution/instances/{iid}").status_code == 200
        assert manager_client.get(f"{API}/execution/instances/{iid}").status_code == 404


def test_execution_writes_are_audited(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        client.post(f"{API}/execution/tasks/{task['id']}/claim")
        client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={"form_data": {"applicant": "审计", "amount": 1}},
        )
    finally:
        client.delete(f"{API}/execution/instances/{iid}")

    logs = client.get(f"{API}/audit", params={"entity_type": "process_task", "limit": 100}).json()
    assert logs["total"] >= 2
    assert any(i["entity_id"] == task["id"] for i in logs["items"])

    instance_logs = client.get(
        f"{API}/audit", params={"entity_type": "process_instance", "limit": 100}
    ).json()
    assert any(i["entity_id"] == iid for i in instance_logs["items"])


# ------------------------------------------------------------------ 上下文与分派


def test_form_data_merges_into_instance_variables(client):
    instance = _start(client)
    iid = instance["id"]
    try:
        task = _open_task(client, iid)
        done = _complete(
            client,
            task["id"],
            form_data={"applicant": "合并测试", "amount": 12345, "description": "上游填写"},
        )
        assert done.status_code == 200, done.text
        detail = client.get(f"{API}/execution/instances/{iid}").json()
        assert detail["variables"]["case"] == "test"
        assert detail["variables"]["applicant"] == "合并测试"
        assert float(detail["variables"]["amount"]) == 12345
        assert detail["variables"]["description"] == "上游填写"
    finally:
        client.delete(f"{API}/execution/instances/{iid}")


def test_assignees_endpoint_excludes_readonly(client, viewer_client):
    rows = client.get(f"{API}/execution/assignees").json()
    assert rows
    assert all(row["role"] != "VIEWER" for row in rows)
    assert any(row["display_name"] == "系统管理员" for row in rows)
    # 只读用户可读取候选人员，但自己不会出现在可指派列表里
    assert viewer_client.get(f"{API}/execution/assignees").status_code == 200
    assert all(
        row["role"] != "VIEWER" for row in viewer_client.get(f"{API}/execution/assignees").json()
    )


def test_candidate_matching_uses_roles_departments_and_orgs():
    from types import SimpleNamespace

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.user import User
    from app.services.execution import _candidate_matches

    with SessionLocal() as db:
        chen = db.scalar(select(User).where(User.username == "chen"))
        assert chen is not None
        # 陈经理属于采购部，可以认领采购部泳道的任务
        assert _candidate_matches(db, chen, "采购部") is True
        # 其他部门的 OWNER 不能认领
        outsider = SimpleNamespace(role="OWNER", department="财务部", org_unit=None)
        assert _candidate_matches(db, outsider, "采购部") is False
        # 角色标签按角色匹配
        assert _candidate_matches(db, outsider, "MANAGER") is False
        assert _candidate_matches(db, outsider, "流程 Owner") is True
        # 无法识别的自由文本不硬拦，交给管理者改派
        assert _candidate_matches(db, outsider, "不存在的泳道") is True


# ------------------------------------------------------------------ 时限与超期


def test_task_due_config_and_overdue_scan(manager_client):
    process_id = _process_id(manager_client, "L3-032")
    original = manager_client.get(
        f"{API}/execution/config", params={"process_id": process_id}
    ).json()["default_task_due_hours"]
    instance = None
    try:
        saved = manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={"default_task_due_hours": 0},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["default_task_due_hours"] == 0

        instance = _start(manager_client)
        iid = instance["id"]
        task = _open_task(manager_client, iid)
        assert task["due_at"] is not None, "配置时限后新任务应有到期时间"

        manager_client.post(f"{API}/notifications/scan")
        summary = manager_client.get(f"{API}/notifications/summary").json()
        assert summary["by_type"].get("TASK_OVERDUE", 0) >= 1

        # 同一任务不应每次扫描都新增未读提醒
        again = manager_client.post(f"{API}/notifications/scan")
        assert again.json()["created"] == 0
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={"default_task_due_hours": original},
        )


def test_viewer_cannot_save_execution_config(viewer_client):
    process_id = _process_id(viewer_client, "L3-032")
    assert (
        viewer_client.get(f"{API}/execution/config", params={"process_id": process_id}).status_code
        == 200
    )
    assert (
        viewer_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={"default_task_due_hours": 24},
        ).status_code
        == 403
    )


# ------------------------------------------------------------------ 结构化节点分派


def _org_id(client, name: str) -> int:
    rows = client.get(f"{API}/org-units").json()
    return next(row["id"] for row in rows if row["name"] == name)


def _user_id(client, display_name: str) -> int:
    rows = client.get(f"{API}/execution/assignees").json()
    return next(row["id"] for row in rows if row["display_name"] == display_name)


def _clear_assignment(client, process_id: int, node_key: str) -> None:
    client.put(
        f"{API}/execution/assignments",
        json={
            "process_id": process_id,
            "node_key": node_key,
            "role": None,
            "org_unit_id": None,
            "default_assignee_user_id": None,
            "due_hours": None,
        },
    )


def test_node_assignment_role_and_due_hours(manager_client, owner_client):
    process_id = _process_id(manager_client, "L3-032")
    instance = None
    try:
        rows = manager_client.get(
            f"{API}/execution/assignments", params={"process_id": process_id}
        ).json()
        assert {row["node_key"] for row in rows} == {"n1", "n2", "n3", "n4", "n5", "n6"}
        assert all(row["role"] is None for row in rows)

        saved = manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "role": "MANAGER",
                "due_hours": 5,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["role_label"] == "流程管理科"
        assert saved.json()["due_hours"] == 5

        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        assert task["node_key"] == "n1"
        assert task["candidate_role_code"] == "MANAGER"
        assert task["due_at"] is not None, "节点时限应覆盖流程默认时限"
        assert task["assignee_user_id"] is None

        # 角色不匹配：流程 Owner 也不能认领
        denied = owner_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert denied.status_code == 403, denied.text
        assert "角色" in denied.json()["detail"]

        allowed = manager_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["assignee_user_id"] is not None
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        _clear_assignment(manager_client, process_id, "n1")

    cleaned = manager_client.get(
        f"{API}/execution/assignments", params={"process_id": process_id}
    ).json()
    assert next(row for row in cleaned if row["node_key"] == "n1")["role"] is None


def test_node_assignment_org_scope(manager_client, owner_client):
    process_id = _process_id(manager_client, "L3-032")
    org_id = _org_id(manager_client, "华东制造部")
    instance = None
    try:
        saved = manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "org_unit_id": org_id,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["org_unit_name"] == "华东制造部"

        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        assert task["candidate_org_unit_id"] == org_id

        # 陈经理属于华东分公司（上级组织），不在此任务限定的组织范围内
        denied = owner_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert denied.status_code == 403, denied.text
        assert "组织" in denied.json()["detail"]

        allowed = manager_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert allowed.status_code == 200, allowed.text
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        _clear_assignment(manager_client, process_id, "n1")


def test_node_assignment_default_assignee(manager_client, owner_client, viewer_client):
    process_id = _process_id(manager_client, "L3-032")
    chen_id = _user_id(manager_client, "陈经理")
    instance = None
    try:
        saved = manager_client.put(
            f"{API}/execution/assignments",
            json={
                "process_id": process_id,
                "node_key": "n1",
                "default_assignee_user_id": chen_id,
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["default_assignee_name"] == "陈经理"

        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        assert task["status"] == "CLAIMED", "默认处理人应直接收到任务"
        assert task["assignee_user_id"] == chen_id
        assert task["assignee_name"] == "陈经理"

        denied = viewer_client.post(f"{API}/execution/tasks/{task['id']}/claim")
        assert denied.status_code == 403

        done = owner_client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={
                "form_data": {"applicant": "陈经理", "amount": 1000, "description": "测试"},
            },
        )
        assert done.status_code == 200, done.text
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        _clear_assignment(manager_client, process_id, "n1")


def test_assignment_writes_are_manager_only(client, manager_client, owner_client, viewer_client):
    process_id = _process_id(manager_client, "L3-032")
    payload = {
        "process_id": process_id,
        "node_key": "n2",
        "role": "OWNER",
    }
    assert viewer_client.put(f"{API}/execution/assignments", json=payload).status_code == 403
    assert owner_client.put(f"{API}/execution/assignments", json=payload).status_code == 403
    assert manager_client.put(f"{API}/execution/assignments", json=payload).status_code == 200
    _clear_assignment(manager_client, process_id, "n2")

    # 默认处理人必须是启用且非只读账号
    users = client.get(f"{API}/auth/users", params={"active_only": True}).json()
    viewer_id = next(row["id"] for row in users if row["username"] == "viewer")
    bad = manager_client.put(
        f"{API}/execution/assignments",
        json={
            "process_id": process_id,
            "node_key": "n2",
            "default_assignee_user_id": viewer_id,
        },
    )
    assert bad.status_code in (400, 422), bad.text
