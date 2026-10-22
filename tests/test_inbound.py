"""入站 Webhook：签名、幂等、流程范围与权限。"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid

import pytest

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _user_id(client, username: str) -> int:
    rows = client.get(f"{API}/auth/users", params={"keyword": username}).json()
    return next(row["id"] for row in rows if row["username"] == username)


def _sign(secret: str, raw: bytes, timestamp: int | None = None) -> dict:
    sent_at = timestamp if timestamp is not None else int(time.time())
    digest = hmac.new(
        secret.encode("utf-8"),
        str(sent_at).encode("utf-8") + b"." + raw,
        hashlib.sha256,
    ).hexdigest()
    return {
        "X-Logix-Timestamp": str(sent_at),
        "X-Logix-Signature": "sha256=" + digest,
        "Content-Type": "application/json",
    }


def _post(client, code: str, body: dict, secret: str, timestamp: int | None = None):
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    return client.post(
        f"{API}/integrations/inbound/{code}",
        content=raw,
        headers=_sign(secret, raw, timestamp),
    )


@pytest.fixture()
def hook(client, manager_client):
    code = "IN-" + uuid.uuid4().hex[:8].upper()
    manager_id = _user_id(client, "manager")
    response = manager_client.post(
        f"{API}/integrations/inbound-hooks",
        json={
            "code": code,
            "name": "ERP 测试入站",
            "run_as_user_id": manager_id,
            "actions": ["start_instance", "complete_task"],
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    yield data
    manager_client.delete(f"{API}/integrations/inbound-hooks/{data['id']}")


def test_create_list_and_permissions(client, manager_client, owner_client, viewer_client):
    process_id = _process_id(manager_client)
    manager_id = _user_id(client, "manager")
    viewer_id = _user_id(client, "viewer")
    owner_id = _user_id(client, "chen")
    code = "IN-" + uuid.uuid4().hex[:8].upper()
    payload = {
        "code": code,
        "name": "ERP 入站",
        "run_as_user_id": manager_id,
        "actions": ["start_instance"],
    }
    try:
        created = manager_client.post(f"{API}/integrations/inbound-hooks", json=payload)
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["secret"], "创建时必须返回一次密钥"
        assert body["inbound_path"].endswith("/integrations/inbound/" + code)
        assert body["process_code"] is None

        rows = manager_client.get(f"{API}/integrations/inbound-hooks").json()
        row = next(item for item in rows if item["id"] == body["id"])
        assert "secret" not in row, "列表不能回传密钥"
        assert row["run_as_user_name"] == "流程管理科"
        assert row["actions"] == ["start_instance"]

        # 只有 MANAGER+ 能维护入站配置
        assert owner_client.get(f"{API}/integrations/inbound-hooks").status_code == 403
        assert (
            viewer_client.post(f"{API}/integrations/inbound-hooks", json=payload).status_code == 403
        )

        # 服务账号必须是启用且 MANAGER/ADMIN
        bad_viewer = manager_client.post(
            f"{API}/integrations/inbound-hooks",
            json={**payload, "code": code + "V", "run_as_user_id": viewer_id},
        )
        assert bad_viewer.status_code == 400, bad_viewer.text
        if owner_id is not None:
            bad_owner = manager_client.post(
                f"{API}/integrations/inbound-hooks",
                json={**payload, "code": code + "O", "run_as_user_id": owner_id},
            )
            assert bad_owner.status_code == 400, bad_owner.text
        # 限定流程时不能只允许完成任务
        scoped = manager_client.post(
            f"{API}/integrations/inbound-hooks",
            json={
                **payload,
                "code": code + "S",
                "process_id": process_id,
                "actions": ["complete_task"],
            },
        )
        assert scoped.status_code == 400, scoped.text
    finally:
        rows = manager_client.get(f"{API}/integrations/inbound-hooks").json()
        for row in rows:
            if row["code"].startswith(code):
                manager_client.delete(f"{API}/integrations/inbound-hooks/{row['id']}")


def test_signed_start_is_idempotent(anon_client, manager_client, hook):
    process_id = _process_id(manager_client)
    body = {
        "event_id": "evt-" + uuid.uuid4().hex,
        "action": "start_instance",
        "process_id": process_id,
        "variables": {"source": "ERP", "order_no": "PO-001"},
    }
    # 不带登录态，凭签名调用
    first = _post(anon_client, hook["code"], body, hook["secret"])
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["duplicate"] is False
    assert result["instance_code"].startswith("PI-")
    iid = result["instance_id"]
    try:
        detail = manager_client.get(f"{API}/execution/instances/{iid}").json()
        assert detail["instance"]["started_by_name"] == "流程管理科"
        assert detail["variables"]["source"] == "ERP"
        assert detail["tasks"][0]["node_key"] == "n1"

        again = _post(anon_client, hook["code"], body, hook["secret"])
        assert again.status_code == 200
        assert again.json()["duplicate"] is True
        assert again.json()["instance_id"] == iid

        events = manager_client.get(
            f"{API}/integrations/inbound-events", params={"hook_id": hook["id"]}
        ).json()
        assert len(events) == 1, "重复请求不应新增入站事件"
        assert events[0]["event_id"] == body["event_id"]
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_signature_and_scope_rejections(anon_client, manager_client, hook):
    process_id = _process_id(manager_client)
    body = {"event_id": "evt-bad", "action": "start_instance", "process_id": process_id}
    raw = json.dumps(body).encode()

    assert (
        anon_client.post(f"{API}/integrations/inbound/{hook['code']}", content=raw).status_code
        == 401
    )
    assert (
        anon_client.post(
            f"{API}/integrations/inbound/{hook['code']}",
            content=raw,
            headers={**_sign(hook["secret"], raw), "X-Logix-Signature": "sha256=deadbeef"},
        ).status_code
        == 401
    )
    assert (
        _post(
            anon_client, hook["code"], body, hook["secret"], timestamp=int(time.time()) - 600
        ).status_code
        == 401
    )
    assert _post(anon_client, "NOPE", body, hook["secret"]).status_code == 404

    other_process = _process_id(manager_client, "L3-033")
    scoped = manager_client.post(
        f"{API}/integrations/inbound-hooks",
        json={
            "code": "IN-" + uuid.uuid4().hex[:8].upper(),
            "name": "限定流程",
            "process_id": process_id,
            "run_as_user_id": hook["run_as_user_id"],
            "actions": ["start_instance"],
        },
    )
    assert scoped.status_code == 201, scoped.text
    scoped_hook = scoped.json()
    iid = None
    try:
        denied = _post(
            anon_client,
            scoped_hook["code"],
            {**body, "event_id": "evt-scope", "process_id": other_process},
            scoped_hook["secret"],
        )
        assert denied.status_code == 403, denied.text

        allowed = _post(
            anon_client,
            scoped_hook["code"],
            {**body, "event_id": "evt-scope-ok", "process_id": None},
            scoped_hook["secret"],
        )
        assert allowed.status_code == 200, allowed.text
        iid = allowed.json()["instance_id"]

        not_allowed = _post(
            anon_client,
            scoped_hook["code"],
            {"event_id": "evt-action", "action": "complete_task", "task_id": 1},
            scoped_hook["secret"],
        )
        assert not_allowed.status_code == 403, not_allowed.text
    finally:
        if iid:
            manager_client.delete(f"{API}/execution/instances/{iid}")
        manager_client.delete(f"{API}/integrations/inbound-hooks/{scoped_hook['id']}")


def test_complete_task_via_inbound(anon_client, manager_client, hook):
    process_id = _process_id(manager_client)
    started = _post(
        anon_client,
        hook["code"],
        {
            "event_id": "evt-start-complete",
            "action": "start_instance",
            "process_id": process_id,
        },
        hook["secret"],
    )
    assert started.status_code == 200, started.text
    iid = started.json()["instance_id"]
    try:
        tasks = manager_client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()
        task = tasks[0]
        body = {
            "event_id": "evt-complete",
            "action": "complete_task",
            "task_id": task["id"],
            "form_data": {"applicant": "ERP", "amount": 1000, "description": "入站完成"},
        }
        done = _post(anon_client, hook["code"], body, hook["secret"])
        assert done.status_code == 200, done.text
        assert done.json()["task_status"] == "COMPLETED"

        open_tasks = manager_client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()
        assert open_tasks and open_tasks[0]["node_key"] == "n2"

        again = _post(anon_client, hook["code"], body, hook["secret"])
        assert again.json()["duplicate"] is True
        still = manager_client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()
        assert still[0]["node_key"] == "n2", "重复完成不应再次推进流程"
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_rotate_and_deactivate(anon_client, manager_client, hook):
    code = hook["code"]
    old_secret = hook["secret"]
    rotated = manager_client.patch(
        f"{API}/integrations/inbound-hooks/{hook['id']}", json={"rotate_secret": True}
    )
    assert rotated.status_code == 200, rotated.text
    new_secret = rotated.json()["secret"]
    assert new_secret and new_secret != old_secret

    body = {
        "event_id": "evt-rotate",
        "action": "start_instance",
        "process_id": _process_id(manager_client),
    }
    assert _post(anon_client, code, body, old_secret).status_code == 401
    iid = None
    try:
        ok = _post(anon_client, code, body, new_secret)
        assert ok.status_code == 200, ok.text
        iid = ok.json()["instance_id"]

        manager_client.patch(
            f"{API}/integrations/inbound-hooks/{hook['id']}", json={"is_active": False}
        )
        disabled = _post(anon_client, code, {**body, "event_id": "evt-disabled"}, new_secret)
        assert disabled.status_code == 403, disabled.text
    finally:
        if iid:
            manager_client.delete(f"{API}/execution/instances/{iid}")
