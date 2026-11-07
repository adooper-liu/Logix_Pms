"""Opt-in real Runner + normal PMS API integration; synthetic identities only."""

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("R3_REAL_ENGINE"), reason="explicit isolated engine required"
)


def test_real_parallel_original_api_and_recovery(client, monkeypatch):
    from sqlalchemy import select

    from app.core.config import settings
    from app.core.database import SessionLocal
    from app.models.execution import NodeAssignment
    from app.models.process import ProcessArch, ProcessModelVersion
    from app.models.user import User
    from app.services import execution_readiness as ready
    from tests.test_engine_bpmn import PARALLEL

    for key, value in {
        "flowable_sandbox_enabled": True,
        "flowable_sandbox_url": "http://127.0.0.1:8136",
        "flowable_sandbox_token": os.environ["FLOWABLE_SANDBOX_TOKEN"],
        "flowable_sandbox_namespace": "logix-r3-sandbox",
    }.items():
        monkeypatch.setattr(type(settings), key, property(lambda self, v=value: v), raising=False)
    made = client.post(
        "/api/v1/process-map",
        json={"code": "R3-REAL-" + uuid.uuid4().hex[:6], "name": "合成并行", "level": 3},
    )
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    saved = client.post(
        f"/api/v1/processes/{pid}/bpmn", json={"xml": PARALLEL, "execution_provider": "FLOWABLE"}
    )
    assert saved.status_code == 200, saved.text
    vid = saved.json()["version_id"]
    with SessionLocal() as db:
        process = db.get(ProcessArch, pid)
        version = db.get(ProcessModelVersion, vid)
        admin = db.scalar(select(User).where(User.username == "admin"))
        version.status = "PUBLISHED"
        from app.core.timeutil import utcnow

        version.published_at = utcnow()
        from app.services.process_model import _apply_snapshot

        _apply_snapshot(db, pid, version.snapshot)
        process.published_model_version = version.version
        for key in ["a", "b"]:
            db.add(NodeAssignment(process_id=pid, node_key=key, default_assignee_user_id=admin.id))
        db.flush()
        config = ready.config_row(db, pid)
        config.readiness = {
            "requirements": {
                k: {"mode": "NOT_APPLICABLE", "reason": "合成沙箱，不代表业务上线"}
                for k in ready.REQUIREMENTS
            }
        }
        config.readiness = {
            **config.readiness,
            "confirmation": {
                "decision": "ACCEPT",
                "fingerprint": ready.get(db, admin, pid)["fingerprint"],
            },
        }
        db.commit()
    deployed = client.post(
        "/api/v1/execution/engine/deploy",
        json={"model_version_id": vid},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert deployed.status_code == 200, deployed.text
    assert deployed.json().get("error") is None, deployed.text
    status = client.get(f"/api/v1/execution/engine/status?process_id={pid}").json()
    assert status["deployment_current"], status
    enabled = client.post(
        "/api/v1/execution/engine/enable",
        json={"process_id": pid, "deployment_id": status["deployment_id"], "enabled": True},
    )
    assert enabled.status_code == 200, enabled.text
    started = client.post(
        "/api/v1/execution/instances",
        json={"process_id": pid},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert started.status_code == 201, started.text
    ident = started.json()["id"]
    detail = client.get(f"/api/v1/execution/instances/{ident}").json()
    assert len(detail["active_tasks"]) == 2, detail
    # manager is not an automatic task participant; disabled users cannot recover old writes.
    manager_token = client.post(
        "/api/v1/auth/login", json={"username": "manager", "password": "manager123"}
    ).json()["token"]
    denied = client.post(
        f"/api/v1/execution/tasks/{detail['active_tasks'][0]['id']}/claim",
        json={},
        headers={"Authorization": "Bearer " + manager_token, "Idempotency-Key": str(uuid.uuid4())},
    )
    assert denied.status_code == 403, denied.text
    # A second business command touching the same instance must wait while the original is unresolved.
    from app.services import engine_commands as command_service

    original = command_service.engine_client

    class PendingClaim:
        def __init__(self):
            self.inner = original()

        def get(self, path):
            return self.inner.get(path)

        def post(self, path, request):
            self.inner.post(path, request)
            raise ConnectionResetError()

    task0 = detail["active_tasks"][0]
    with monkeypatch.context() as patch:
        patch.setattr(command_service, "engine_client", PendingClaim)
        claiming = client.post(
            f"/api/v1/execution/tasks/{task0['id']}/claim",
            json={},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert claiming.status_code == 202, claiming.text
        unknown_view = client.get(f"/api/v1/execution/instances/{ident}").json()
        assert unknown_view["instance"]["sync_status"] != "CURRENT", (
            "Unresolved engine writes must be visible in original instance detail"
        )
    overlap = client.post(
        f"/api/v1/execution/instances/{ident}/cancel",
        json={},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert overlap.status_code == 409, overlap.text
    restored_claim = client.post(
        f"/api/v1/execution/engine/commands/{claiming.json()['command_id']}/recover", json={}
    )
    assert restored_claim.status_code == 200, restored_claim.text
    for index, task in enumerate(detail["active_tasks"]):
        completed = client.post(
            f"/api/v1/execution/tasks/{task['id']}/complete",
            json={},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert completed.status_code == 200, completed.text
        assert completed.json()["completed_by_name"] == "系统管理员", completed.text
        status = client.get(f"/api/v1/execution/instances/{ident}").json()
        assert status["instance"]["status"] == ("RUNNING" if index == 0 else "COMPLETED"), status
    print("REAL ENGINE original API parallel join PASS", ident)
    # Commit succeeded remotely but the HTTP response is lost: 202, same durable ID, fresh-session recovery.
    from app.services import engine_commands, engine_projection

    original_client = engine_commands.engine_client

    class LostResponse:
        def __init__(self):
            self.inner = original_client()

        def get(self, path):
            return self.inner.get(path)

        def post(self, path, request):
            self.inner.post(path, request)
            raise ConnectionResetError("injected response loss after engine commit")

    with monkeypatch.context() as patch:
        patch.setattr(engine_commands, "engine_client", LostResponse)
        uncertain = client.post(
            "/api/v1/execution/instances",
            json={"process_id": pid},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert uncertain.status_code == 202, uncertain.text
    if os.getenv("R3_RESTART_ENGINE"):
        import subprocess

        env = os.environ.copy()
        env["MSYS_NO_PATHCONV"] = "1"
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--env-file",
                "var/r3-sandbox/empty.env",
                "-f",
                "engine/flowable-runner/compose.sandbox.yml",
                "restart",
                "runner",
            ],
            env=env,
            capture_output=True,
        )
        assert result.returncode == 0, "Dedicated sandbox restart failed"
        from app.services.engine_transport import engine_client
        from scripts.verify_flowable_poc import wait_for

        def ready_after_restart():
            try:
                return bool(engine_client().check())
            except Exception:
                return False

        wait_for(ready_after_restart, bool, timeout=90)
        print("Observed sandbox Runner restart before fresh PMS session recovery")
    restored = client.post(
        f"/api/v1/execution/engine/commands/{uncertain.json()['command_id']}/recover", json={}
    )
    assert restored.status_code == 200 and restored.json()["open_task_count"] == 2, restored.text
    # Local projection failure must retain confirmed receipt and can be applied again without a second START.
    with monkeypatch.context() as patch:
        patch.setattr(
            engine_projection,
            "reconcile",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("local apply failed")),
        )
        unapplied = client.post(
            "/api/v1/execution/instances",
            json={"process_id": pid},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert unapplied.status_code == 202, unapplied.text
    applied = client.post(
        f"/api/v1/execution/engine/commands/{unapplied.json()['command_id']}/recover", json={}
    )
    assert applied.status_code == 200 and applied.json()["open_task_count"] == 2, applied.text
    # An exact COMPLETE replay is valid even after the local task is terminal; changed form data conflicts.
    pending = client.get(f"/api/v1/execution/instances/{applied.json()['id']}").json()[
        "active_tasks"
    ][0]
    completion_key = str(uuid.uuid4())
    first = client.post(
        f"/api/v1/execution/tasks/{pending['id']}/complete",
        json={"comment": "original"},
        headers={"Idempotency-Key": completion_key},
    )
    assert first.status_code == 200, first.text
    replay = client.post(
        f"/api/v1/execution/tasks/{pending['id']}/complete",
        json={"comment": "original"},
        headers={"Idempotency-Key": completion_key},
    )
    assert replay.status_code == 200, replay.text
    changed = client.post(
        f"/api/v1/execution/tasks/{pending['id']}/complete",
        json={"comment": "different"},
        headers={"Idempotency-Key": completion_key},
    )
    assert changed.status_code == 409, changed.text
    from app.models.execution import ProcessTask

    with SessionLocal() as db:
        assert db.get(ProcessTask, pending["id"]).comment == "original", (
            "Conflicting replay must not overwrite original local form"
        )
    # Direct completion must retain local form/comment/worklog exactly once, including replay.
    pending2 = client.get(f"/api/v1/execution/instances/{applied.json()['id']}").json()[
        "active_tasks"
    ][0]
    effort_key = str(uuid.uuid4())
    effort_payload = {"effort_minutes": 12, "comment": "measured sandbox work"}
    effort = client.post(
        f"/api/v1/execution/tasks/{pending2['id']}/complete",
        json=effort_payload,
        headers={"Idempotency-Key": effort_key},
    )
    assert effort.status_code == 200, effort.text
    assert effort.json()["actual_minutes"] == 12, effort.text
    effort_replay = client.post(
        f"/api/v1/execution/tasks/{pending2['id']}/complete",
        json=effort_payload,
        headers={"Idempotency-Key": effort_key},
    )
    assert effort_replay.status_code == 200 and effort_replay.json()["actual_minutes"] == 12
    assert len(client.get(f"/api/v1/execution/tasks/{pending2['id']}/worklogs").json()) == 1
    print("REAL ENGINE response loss / local apply retry / exact complete replay PASS")
    # Consume a real journal page for THIS context; no artificial global history from other test databases.
    from sqlalchemy import func

    from app.models.engine import EngineCursor, EngineInbox
    from app.models.execution import ProcessInstance
    from app.models.notification import Notification

    transport = original_client()
    all_events = []
    cursor = 0
    while True:
        page = transport.get(f"/events?after_id={cursor}&limit=500")
        all_events.extend(page["events"])
        cursor = page["next_after_id"]
        if not page["has_more"]:
            break
    instance_id = applied.json()["id"]
    with SessionLocal() as db:
        engine_id = db.get(ProcessInstance, instance_id).engine_instance_id
    current = [e for e in all_events if e.get("engine_instance_id") == engine_id]
    assert current and all(
        e.get("context", {}).get("namespace") == "logix-r3-sandbox" for e in current
    )
    from types import SimpleNamespace

    snapshot = transport.get("/instances/" + engine_id)
    fake_page = {"events": current, "next_after_id": cursor, "has_more": False}

    def read(path):
        return fake_page if path.startswith("/events") else snapshot

    with monkeypatch.context() as patch:
        patch.setattr(
            engine_projection,
            "engine_client",
            lambda: SimpleNamespace(namespace="logix-r3-sandbox", get=read),
        )
        with SessionLocal() as db:
            engine_projection.consume(db)
            count = db.scalar(select(func.count()).select_from(Notification))
            received = db.scalar(select(func.count()).select_from(EngineInbox))
            engine_projection.consume(db)
            assert db.scalar(select(func.count()).select_from(Notification)) == count
            assert db.scalar(select(func.count()).select_from(EngineInbox)) == received
            baseline = db.get(EngineCursor, "logix-r3-sandbox").after_id
        bad_event = {
            **current[-1],
            "event_id": str(uuid.uuid4()),
            "definition_id": "foreign-definition",
        }
        fake_page["events"] = [bad_event]
        fake_page["next_after_id"] = cursor + 1
        with SessionLocal() as db:
            from fastapi import HTTPException

            with pytest.raises(HTTPException):
                engine_projection.consume(db)
            assert db.get(EngineCursor, "logix-r3-sandbox").after_id == baseline
    # Exercise the supported control commands through the same public API.
    controlled = client.post(
        "/api/v1/execution/instances",
        json={"process_id": pid},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert controlled.status_code == 201, controlled.text
    control_id = controlled.json()["id"]
    controlled_tasks = client.get(f"/api/v1/execution/instances/{control_id}").json()[
        "active_tasks"
    ]
    assigned = client.patch(
        f"/api/v1/execution/tasks/{controlled_tasks[0]['id']}/assignee",
        json={"assignee_user_id": admin.id},
        headers={"Idempotency-Key": str(uuid.uuid4())},
    )
    assert assigned.status_code == 200 and assigned.json()["assignee_user_id"] == admin.id, (
        assigned.text
    )
    for action, expected in [
        ("suspend", "SUSPENDED"),
        ("resume", "RUNNING"),
        ("cancel", "CANCELLED"),
    ]:
        result = client.post(
            f"/api/v1/execution/instances/{control_id}/{action}",
            json={},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        assert result.status_code == 200 and result.json()["status"] == expected, result.text
    assert all(
        t["status"] == "CANCELLED"
        for t in client.get(f"/api/v1/execution/instances/{control_id}").json()["tasks"]
    )
    # Recovery requires current active identity and current organization visibility, even for original commands.
    from fastapi import HTTPException

    from app.models.org import OrgUnit
    from app.services import engine_execution

    with SessionLocal() as db:
        inactive = SimpleNamespace(id=admin.id, is_active=False, role="ADMIN")
        with pytest.raises(HTTPException) as denied:
            engine_execution.recover(db, inactive, uncertain.json()["command_id"])
        assert denied.value.status_code == 403
        process = db.get(ProcessArch, pid)
        org = db.scalar(select(OrgUnit).order_by(OrgUnit.id))
        assert org is not None
        process.org_unit_id = org.id
        outsider = SimpleNamespace(id=admin.id, is_active=True, role="OWNER", org_unit_id=None)
        with pytest.raises(HTTPException) as denied:
            engine_execution.instance_visible(db, outsider, db.get(ProcessInstance, control_id))
        assert denied.value.status_code == 404
        db.rollback()
    print("REAL ENGINE assign/suspend/resume/cancel / disabled recovery / organization denial PASS")
    # Stale preparation must disable new starts, but must not prevent turning them off.
    with SessionLocal() as db:
        assignment = db.scalar(
            select(NodeAssignment).where(
                NodeAssignment.process_id == pid, NodeAssignment.node_key == "a"
            )
        )
        assignment.default_assignee_user_id = db.scalar(
            select(User.id).where(User.username == "manager")
        )
        db.commit()
    stale = client.get(f"/api/v1/execution/engine/status?process_id={pid}").json()
    assert stale["allow_start"] is False
    listed = next(p for p in client.get("/api/v1/execution/processes").json() if p["id"] == pid)
    assert listed["can_start"] is False, "Original start modal must also reject stale deployment"
    stopped = client.post(
        "/api/v1/execution/engine/enable",
        json={
            "process_id": pid,
            "deployment_id": client.get(f"/api/v1/execution/engine/status?process_id={pid}").json()[
                "deployment_id"
            ],
            "enabled": False,
        },
    )
    assert stopped.status_code == 200, stopped.text
    print("REAL ENGINE event replay / notification dedup / wrong-definition cursor rollback PASS")
