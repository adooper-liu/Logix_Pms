"""执行层正确性：幂等、任务事件、并发条件更新、单 OPEN 约束、挂起 SLA。"""

from __future__ import annotations

import time
import uuid
from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

API = "/api/v1"


def _process_id(client, code: str = "L3-032") -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def _start(client, code: str = "L3-032", **headers) -> dict:
    response = client.post(
        f"{API}/execution/instances",
        json={"process_id": _process_id(client, code)},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _open_task(client, instance_id: int) -> dict:
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    assert tasks
    return tasks[0]


def _events(client, task_id: int) -> list[dict]:
    response = client.get(f"{API}/execution/tasks/{task_id}/events")
    assert response.status_code == 200, response.text
    return response.json()


def test_idempotent_start(manager_client):
    key = "start-" + uuid.uuid4().hex
    instance = None
    try:
        first = _start(manager_client, **{"Idempotency-Key": key})
        second = _start(manager_client, **{"Idempotency-Key": key})
        assert second["id"] == first["id"]
        assert second["code"] == first["code"]
        instance = first

        # 同一个 key 换参数必须拒绝，避免把错误响应回放给另一个请求
        other = manager_client.post(
            f"{API}/execution/instances",
            json={"process_id": _process_id(manager_client, "L3-033")},
            headers={"Idempotency-Key": key},
        )
        assert other.status_code == 409, other.text
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")


def test_idempotent_complete_and_task_events(manager_client, owner_client):
    key = "complete-" + uuid.uuid4().hex
    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        created = _events(manager_client, task["id"])
        assert [e["event_type"] for e in created] == ["CREATED"]
        assert created[0]["actor_name"] == "流程管理科"

        assert owner_client.post(f"{API}/execution/tasks/{task['id']}/claim").status_code == 200
        claimed = _events(manager_client, task["id"])
        assert [e["event_type"] for e in claimed] == ["CREATED", "CLAIMED"]
        assert claimed[-1]["actor_name"] == "陈经理"

        payload = {"form_data": {"applicant": "陈经理", "amount": 1000, "description": "幂等测试"}}
        first = owner_client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert first.status_code == 200, first.text
        second = owner_client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert second.status_code == 200, second.text
        assert second.json()["id"] == first.json()["id"]
        assert second.json()["status"] == "COMPLETED"

        open_tasks = manager_client.get(
            f"{API}/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()
        assert len(open_tasks) == 1 and open_tasks[0]["node_key"] == "n2"

        completed = _events(manager_client, task["id"])
        assert [e["event_type"] for e in completed] == [
            "CREATED",
            "CLAIMED",
            "COMPLETED",
        ]
        assert completed[-1]["actor_name"] == "陈经理"
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_stale_claim_is_rejected(manager_client):
    from app.core.database import SessionLocal
    from app.core.timeutil import utcnow
    from app.models.execution import ProcessTask
    from app.models.user import User
    from app.services import execution as execution_service

    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        with SessionLocal() as s1, SessionLocal() as s2:
            stale = s1.get(ProcessTask, task["id"])
            fresh = s2.get(ProcessTask, task["id"])
            manager = s2.scalar(select(User).where(User.username == "manager"))
            chen = s1.scalar(select(User).where(User.username == "chen"))
            execution_service.claim_task(s2, fresh, manager)
            s2.commit()

            # 条件更新本身必须拒绝旧 row_version（即使调用方绕过了 refresh）
            assert (
                execution_service._claim_update(
                    s1,
                    stale,
                    assignee=chen,
                    status="CLAIMED",
                    claimed_at=utcnow(),
                )
                is False
            )

            # 走正常入口时，refresh 后看到已被认领，同样不能覆盖
            with pytest.raises(HTTPException) as exc:
                execution_service.claim_task(s1, stale, chen)
            assert exc.value.status_code in (403, 409)
            s1.rollback()

        current = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        assert current["assignee_name"] == "流程管理科"
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_stale_complete_is_rejected(manager_client, owner_client):
    from app.core.database import SessionLocal
    from app.models.execution import ProcessTask
    from app.models.user import User
    from app.schemas.execution import TaskCompleteRequest
    from app.services import execution as execution_service

    instance = _start(manager_client)
    iid = instance["id"]
    try:
        task = _open_task(manager_client, iid)
        with SessionLocal() as s1, SessionLocal() as s2:
            stale = s1.get(ProcessTask, task["id"])
            fresh = s2.get(ProcessTask, task["id"])
            manager = s2.scalar(select(User).where(User.username == "manager"))
            chen = s1.scalar(select(User).where(User.username == "chen"))
            payload = TaskCompleteRequest(
                form_data={"applicant": "经理", "amount": 1, "description": "先完成"}
            )
            execution_service.complete_task(s2, fresh, manager, payload)
            s2.commit()

            with pytest.raises(HTTPException) as exc:
                execution_service.complete_task(s1, stale, chen, payload)
            assert exc.value.status_code == 409
            s1.rollback()
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_one_open_task_database_guard(manager_client):
    from app.core.database import SessionLocal
    from app.models.execution import ProcessTask

    instance = _start(manager_client)
    iid = instance["id"]
    try:
        with SessionLocal() as db:
            db.add(
                ProcessTask(
                    instance_id=iid,
                    node_key="duplicate",
                    name="重复待办",
                    task_type="TASK",
                    status="PENDING",
                )
            )
            with pytest.raises(IntegrityError):
                db.flush()
            db.rollback()
    finally:
        manager_client.delete(f"{API}/execution/instances/{iid}")


def test_suspend_shifts_due_and_records_sla_event(manager_client):
    process_id = _process_id(manager_client)
    original = manager_client.get(
        f"{API}/execution/config", params={"process_id": process_id}
    ).json()
    instance = None
    try:
        manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={
                "default_task_due_hours": 24,
                "default_escalation_hours": None,
                "default_escalation_user_id": None,
            },
        )
        instance = _start(manager_client)
        task = _open_task(manager_client, instance["id"])
        before = datetime.fromisoformat(task["due_at"])

        manager_client.post(
            f"{API}/execution/instances/{instance['id']}/suspend",
            json={"reason": "SLA 测试"},
        )
        time.sleep(0.2)
        manager_client.post(f"{API}/execution/instances/{instance['id']}/resume")

        after_task = manager_client.get(f"{API}/execution/tasks/{task['id']}").json()
        after = datetime.fromisoformat(after_task["due_at"])
        assert after > before, "挂起期间不应消耗 SLA"

        events = _events(manager_client, task["id"])
        assert "SLA_SHIFTED" in [e["event_type"] for e in events]
    finally:
        if instance is not None:
            manager_client.delete(f"{API}/execution/instances/{instance['id']}")
        manager_client.put(
            f"{API}/execution/config",
            params={"process_id": process_id},
            json={
                "default_task_due_hours": original["default_task_due_hours"],
                "default_escalation_hours": original["default_escalation_hours"],
                "default_escalation_user_id": original["default_escalation_user_id"],
            },
        )
