"""M6原执行配置的上线准备、本人确认及十层适用性。"""

from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def ready_process(client):
    me = client.get(API + "/auth/me").json()
    proc = client.post(
        API + "/process-map",
        json={
            "code": "READY-" + uuid4().hex[:8],
            "name": "上线准备测试",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()
    pid = proc["id"]
    activity = client.post(
        API + "/process-map",
        json={
            "code": "READY-A-" + uuid4().hex[:8],
            "name": "上线活动",
            "level": 4,
            "parent_id": pid,
        },
    ).json()
    from binding_test_helpers import position_role, remove_position_roles
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.org import Position
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.models.raci import RaciAssignment
    from app.models.workload import WorkMeasurementStandard

    with SessionLocal() as db:
        position = Position(code="READY-P-" + uuid4().hex[:8], name="上线岗位")
        db.add(position)
        db.flush()
        posid = position.id
        role, _member = position_role(db, posid)
        db.add(
            RaciAssignment(
                process_id=pid,
                activity_id=activity["id"],
                role_id=role.id,
                matter="上线负责",
                raci="A",
            )
        )
        db.add(
            WorkMeasurementStandard(
                code="READY-S-" + uuid4().hex[:8],
                name="已验证工时",
                activity_id=activity["id"],
                position_id=posid,
                status="VERIFIED",
                standard_minutes=5,
            )
        )
        carrier = ProcessDocument(
            process_id=activity["id"],
            code="READY-C-" + uuid4().hex[:8],
            title="上线记录",
            category="FORM",
        )
        db.add(carrier)
        db.flush()
        db.add(
            ProcessDocumentVersion(document_id=carrier.id, version_label="1.0", status="EFFECTIVE")
        )
        db.commit()
    saved = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [
                {"node_key": "s", "name": "开始", "node_type": "START"},
                {
                    "node_key": "a",
                    "name": "办理",
                    "node_type": "TASK",
                    "process_arch_id": activity["id"],
                    "owner_position_id": posid,
                },
                {"node_key": "e", "name": "结束", "node_type": "END"},
            ],
            "edges": [
                {"source_key": "s", "target_key": "a"},
                {"source_key": "a", "target_key": "e"},
            ],
        },
    )
    assert saved.status_code == 200, saved.text
    client.post(f"{API}/processes/{pid}/design/submit-review", json={"note": "本轮评审"})
    published = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"change_note": "本轮发布原模型", "self_publish_reason": "隔离测试验证当前运行版本"},
    )
    assert published.status_code == 200, published.text
    yield (
        pid,
        published.json()["id"] if "id" in published.json() else published.json()["version_id"],
    )
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.models.execution import (
        NodeAssignment,
        ProcessExecutionConfig,
        ProcessInstance,
        ProcessTask,
    )
    from app.models.pilot import PilotLayer, PilotPath

    with SessionLocal() as db:
        path_ids = list(db.scalars(select(PilotPath.id).where(PilotPath.process_id == pid)))
        db.execute(delete(PilotLayer).where(PilotLayer.path_id.in_(path_ids)))
        db.execute(delete(PilotPath).where(PilotPath.id.in_(path_ids)))
        instances = list(
            db.scalars(select(ProcessInstance).where(ProcessInstance.process_id == pid))
        )
        for instance in instances:
            for task in db.scalars(
                select(ProcessTask).where(ProcessTask.instance_id == instance.id)
            ).all():
                db.delete(task)
            db.flush()
            db.delete(instance)
        db.flush()
        db.execute(delete(ProcessExecutionConfig).where(ProcessExecutionConfig.process_id == pid))
        db.execute(delete(NodeAssignment).where(NodeAssignment.process_id == pid))
        db.commit()
    with SessionLocal() as db:
        document_ids = select(ProcessDocument.id).where(
            ProcessDocument.process_id == activity["id"]
        )
        db.execute(
            delete(ProcessDocumentVersion).where(
                ProcessDocumentVersion.document_id.in_(document_ids)
            )
        )
        db.execute(delete(ProcessDocument).where(ProcessDocument.process_id == activity["id"]))
        db.execute(delete(RaciAssignment).where(RaciAssignment.process_id == pid))
        db.execute(
            delete(WorkMeasurementStandard).where(WorkMeasurementStandard.position_id == posid)
        )
        db.commit()
    deleted = client.delete(f"{API}/process-map/{pid}")
    assert deleted.status_code == 200, deleted.text
    with SessionLocal() as db:
        remove_position_roles(db, [posid])
        db.delete(db.get(Position, posid))
        db.commit()


def ready_payload(client, revision):
    reviewer = next(
        row for row in client.get(API + "/auth/users").json() if row["username"] == "chen"
    )
    return {
        "expected_revision": revision,
        "reviewer_user_id": reviewer["id"],
        "requirements": {
            key: {
                "mode": "NOT_APPLICABLE",
                "reason": "本流程经核对采用人工公开队列且不需结构化字段/时限",
            }
            for key in ("forms", "assignments", "deadlines")
        },
        "evidence": "原场景/权限/异常恢复核对记录",
        "rollback_note": "停止新实例并沿原发布回退，旧在途按原版本处理",
    }


def test_readiness_personal_confirmation_and_stale_config(client, owner_client, ready_process):
    pid, vid = ready_process
    path = API + f"/execution/readiness?process_id={pid}"
    before = client.get(path)
    assert before.status_code == 200, before.text
    assert before.json()["published_model_version_id"] == vid
    assert not before.json()["confirmed"]
    saved = client.put(path, json=ready_payload(client, before.json()["revision"]))
    assert saved.status_code == 200, saved.text
    payload = {
        "expected_revision": saved.json()["revision"],
        "decision": "ACCEPT",
        "evidence": "本人核对适用性/发布及回退",
    }
    assert (
        client.post(
            API + f"/execution/readiness/confirm?process_id={pid}", json=payload
        ).status_code
        == 403
    )
    confirmed = owner_client.post(
        API + f"/execution/readiness/confirm?process_id={pid}", json=payload
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmed"] is True
    assert (
        client.put(
            API + f"/execution/config?process_id={pid}", json={"default_task_due_hours": 4}
        ).status_code
        == 200
    )
    changed = client.get(path).json()
    assert changed["confirmed"] is False
    assert changed["state_label"] == "准备依据已变化，待复核"


def test_readiness_exposes_original_facts_and_backend_labels(client, ready_process):
    pid, _ = ready_process
    result = client.get(API + f"/execution/readiness?process_id={pid}").json()
    assert result["facts"] == {"forms": False, "assignments": False, "deadlines": False}
    assert set(result["requirement_labels"]) == {"forms", "assignments", "deadlines"}
    assert set(result["mode_labels"]) == {"REQUIRED", "NOT_APPLICABLE"}


def test_required_configuration_blocks_accept_and_revision_replay(
    client, owner_client, ready_process
):
    pid, _ = ready_process
    path = API + f"/execution/readiness?process_id={pid}"
    payload = ready_payload(client, 0)
    payload["requirements"]["forms"] = {"mode": "REQUIRED", "reason": "业务字段需要核对"}
    saved = client.put(path, json=payload)
    assert saved.status_code == 200, saved.text
    assert "结构化任务表单未完整配置" in saved.json()["missing"]
    assert client.put(path, json=payload).status_code == 409
    confirmed = owner_client.post(
        API + f"/execution/readiness/confirm?process_id={pid}",
        json={"expected_revision": 1, "decision": "ACCEPT", "evidence": "本人核对"},
    )
    assert confirmed.status_code == 400, confirmed.text


def test_instance_stores_original_published_primary_key(client, ready_process):
    pid, vid = ready_process
    started = client.post(API + "/execution/instances", json={"process_id": pid})
    assert started.status_code == 201, started.text
    assert started.json()["model_version_id"] == vid
    assert started.json()["round_id"] is None
    instance_id = started.json()["id"]
    changed = client.put(
        f"{API}/processes/{pid}/design",
        json={
            "nodes": [{"node_key": "a", "name": "新办理", "node_type": "TASK"}],
            "edges": [],
        },
    )
    assert changed.status_code == 200, changed.text
    client.post(f"{API}/processes/{pid}/design/submit-review", json={"note": "新版本评审"})
    republished = client.post(
        f"{API}/processes/{pid}/design/publish",
        json={"change_note": "下一运行版本", "self_publish_reason": "隔离测试核对旧实例不切版本"},
    )
    assert republished.status_code == 200, republished.text
    detail = client.get(f"{API}/execution/instances/{instance_id}").json()
    assert detail["instance"]["model_version_id"] == vid
    from app.core.database import SessionLocal
    from app.models.execution import ProcessInstance

    with SessionLocal() as db:
        snapshot = db.get(ProcessInstance, instance_id).snapshot
        assert snapshot["model_version_id"] == vid
        assert next(n for n in snapshot["nodes"] if n["key"] == "a")["name"] == "办理"


def test_pilot_applicability_is_typed_and_core_requirements_cannot_be_waived(client, ready_process):
    pid, _ = ready_process
    path = client.post(API + "/pilot/paths", json={"process_id": pid}).json()
    url = API + f"/pilot/paths/{path['id']}/layers/6/applicability"
    invalid = client.put(
        url,
        json={
            "expected_revision": 0,
            "requirements": {"rpa_bots": {"mode": "REQUIRED", "reason": None}},
        },
    )
    assert invalid.status_code == 422, invalid.text
    payload = {
        "expected_revision": 0,
        "requirements": {"rpa_bots": {"mode": "REQUIRED", "reason": "本流程确需机器人"}},
    }
    saved = client.put(url, json=payload)
    assert saved.status_code == 200, saved.text
    layer = saved.json()["layers"][5]
    bot = next(i for i in layer["evidence_items"] if i["key"] == "rpa_bots")
    assert bot["required"] and not layer["gate_open"]
    assert bot["applicability_label"] == "必需"
    assert client.put(url, json=payload).status_code == 409
    assert client.put(url.replace("/6/", "/1/"), json=payload).status_code == 400
    assert (
        client.put(API + "/pilot/paths/999999/layers/6/applicability", json=payload).status_code
        == 404
    )


def test_round_start_rejects_stale_readiness_and_pins_identity(client, owner_client, ready_process):
    from sqlalchemy import delete, select

    from app.core.database import SessionLocal
    from app.models.improvement_round import ProcessImprovementRound

    pid, vid = ready_process
    with SessionLocal() as db:
        row = ProcessImprovementRound(
            process_id=pid, name="运行身份", scope_note="测试", released_model_version_id=vid
        )
        db.add(row)
        db.commit()
        rid = row.id
    try:
        payload = {"process_id": pid, "round_id": rid}
        assert client.post(API + "/execution/instances", json=payload).status_code == 409
        saved = client.put(
            API + f"/execution/readiness?process_id={pid}", json=ready_payload(client, 0)
        )
        assert saved.status_code == 200, saved.text
        owner_client.post(
            API + f"/execution/readiness/confirm?process_id={pid}",
            json={"expected_revision": 1, "decision": "ACCEPT", "evidence": "核对"},
        )
        started = client.post(API + "/execution/instances", json=payload)
        assert started.status_code == 201, started.text
        assert started.json()["round_id"] == rid and started.json()["model_version_id"] == vid
        client.put(API + f"/execution/config?process_id={pid}", json={"default_task_due_hours": 5})
        assert client.post(API + "/execution/instances", json=payload).status_code == 409
    finally:
        from app.models.execution import ProcessInstance

        with SessionLocal() as db:
            for instance in db.scalars(
                select(ProcessInstance).where(ProcessInstance.round_id == rid)
            ).all():
                instance.round_id = None
            db.flush()
            db.execute(delete(ProcessImprovementRound).where(ProcessImprovementRound.id == rid))
            db.commit()


def test_start_idempotency_does_not_replay_another_users_instance(
    client, owner_client, ready_process
):
    pid, _ = ready_process
    key = uuid4().hex
    payload = {"process_id": pid}
    original = client.post(
        API + "/execution/instances", json=payload, headers={"Idempotency-Key": key}
    )
    assert original.status_code == 201, original.text
    replay = client.post(
        API + "/execution/instances", json=payload, headers={"Idempotency-Key": key}
    )
    assert replay.json()["id"] == original.json()["id"]
    other = owner_client.post(
        API + "/execution/instances", json=payload, headers={"Idempotency-Key": key}
    )
    assert other.status_code == 201, other.text
    assert other.json()["id"] != original.json()["id"]


def test_process_with_direct_instance_model_reference_rejects_deletion(client, ready_process):
    pid, _ = ready_process
    started = client.post(API + "/execution/instances", json={"process_id": pid})
    assert started.status_code == 201, started.text
    deleted = client.delete(API + f"/process-map/{pid}")
    assert deleted.status_code == 409, deleted.text
    assert client.get(API + f"/processes/{pid}/design").status_code == 200


def test_assignment_requires_routing_not_only_sla(client, ready_process):
    pid, _ = ready_process
    saved = client.put(
        API + "/execution/assignments", json={"process_id": pid, "node_key": "a", "due_hours": 4}
    )
    assert saved.status_code == 200, saved.text
    facts = client.get(API + f"/execution/readiness?process_id={pid}").json()["facts"]
    assert facts["assignments"] is False
    assert facts["deadlines"] is True


def test_inactive_handler_invalidates_required_assignment(client, owner_client, ready_process):
    from app.core.database import SessionLocal
    from app.models.user import User

    pid, _ = ready_process
    reviewer = ready_payload(client, 0)["reviewer_user_id"]
    client.put(
        API + "/execution/assignments",
        json={"process_id": pid, "node_key": "a", "default_assignee_user_id": reviewer},
    )
    payload = ready_payload(client, 0)
    payload["requirements"]["assignments"] = {"mode": "REQUIRED", "reason": "必须有处理人"}
    client.put(API + f"/execution/readiness?process_id={pid}", json=payload)
    confirmed = owner_client.post(
        API + f"/execution/readiness/confirm?process_id={pid}",
        json={"expected_revision": 1, "decision": "ACCEPT", "evidence": "本人核对"},
    )
    assert confirmed.json()["confirmed"], confirmed.text
    try:
        with SessionLocal() as db:
            db.get(User, reviewer).is_active = False
            db.commit()
        changed = client.get(API + f"/execution/readiness?process_id={pid}").json()
        assert changed["confirmed"] is False
        assert changed["facts"]["assignments"] is False
        assert changed["fingerprint"] != confirmed.json()["fingerprint"]
    finally:
        with SessionLocal() as db:
            db.get(User, reviewer).is_active = True
            db.commit()


def test_mixed_task_requirements_are_evaluated_per_node(client, owner_client, ready_process):
    pid, _ = ready_process
    payload = ready_payload(client, 0)
    payload["requirements"]["forms"] = {"mode": "REQUIRED", "reason": "默认需要表单"}
    payload["node_requirements"] = {
        "a": {"forms": {"mode": "NOT_APPLICABLE", "reason": "此任务不收字段"}}
    }
    saved = client.put(API + f"/execution/readiness?process_id={pid}", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["readiness"]["node_requirements"] == payload["node_requirements"]
    confirmed = owner_client.post(
        API + f"/execution/readiness/confirm?process_id={pid}",
        json={"expected_revision": 1, "decision": "ACCEPT", "evidence": "逐任务核对"},
    )
    assert confirmed.status_code == 200 and confirmed.json()["confirmed"], confirmed.text
    payload["expected_revision"] = 2
    payload["node_requirements"] = {
        "wrong": {"forms": {"mode": "NOT_APPLICABLE", "reason": "错节点"}}
    }
    assert (
        client.put(API + f"/execution/readiness?process_id={pid}", json=payload).status_code == 400
    )


def test_legacy_successful_start_key_replays_without_new_instance(client, ready_process):
    import hashlib
    import json

    from app.core.database import SessionLocal
    from app.models.execution import IdempotencyRecord
    from app.schemas.execution import InstanceStartRequest

    pid, _ = ready_process
    original = client.post(API + "/execution/instances", json={"process_id": pid}).json()
    key = uuid4().hex
    old_payload = InstanceStartRequest(process_id=pid).model_dump(mode="json", exclude={"round_id"})
    digest = hashlib.sha256(
        json.dumps(old_payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()
    with SessionLocal() as db:
        db.add(
            IdempotencyRecord(
                scope="instance.start",
                key=key,
                request_hash=digest,
                status="SUCCESS",
                response=original,
            )
        )
        db.commit()
    replay = client.post(
        API + "/execution/instances", json={"process_id": pid}, headers={"Idempotency-Key": key}
    )
    assert replay.status_code == 201, replay.text
    assert replay.json()["id"] == original["id"]


def test_pilot_get_does_not_write_and_technology_optional(client, ready_process):
    from sqlalchemy import delete, func, select

    from app.core.database import SessionLocal
    from app.models.pilot import PilotLayer, PilotPath

    pid, vid = ready_process
    created = client.post(API + "/pilot/paths", json={"process_id": pid}).json()
    ident = created["id"]
    try:
        with SessionLocal() as db:
            row = db.get(PilotPath, ident)
            row.current_layer = 9
            db.execute(
                delete(PilotLayer).where(PilotLayer.path_id == ident, PilotLayer.layer_no == 6)
            )
            db.commit()
            before = db.scalar(select(func.count()).select_from(PilotLayer))
        detail = client.get(API + f"/pilot/paths/{ident}").json()
        layer = detail["layers"][5]
        assert all(
            not item["required"]
            for item in layer["evidence_items"]
            if item["key"]
            in ("rpa_bots", "rpa_runs", "technology_uses", "process_cases", "mining_variants")
        )
        with SessionLocal() as db:
            assert db.get(PilotPath, ident).current_layer == 9
            assert db.scalar(select(func.count()).select_from(PilotLayer)) == before
    finally:
        client.delete(API + f"/pilot/paths/{ident}")
