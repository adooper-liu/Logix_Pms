"""M8原Gate用途与同轮正式核验边界。"""

from uuid import uuid4

import pytest
from test_publish_gate_bindings import gate_case as shared_gate_case

gate_case = pytest.fixture(name="gate_case")(shared_gate_case.__wrapped__)

API = "/api/v1"


@pytest.fixture
def outcome_scope(client):
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.core.timeutil import utcnow
    from app.models.improvement_round import ProcessImprovementRound
    from app.models.maturity import GateAttestation
    from app.models.process import ProcessArch
    from app.services.process_model import ensure_baseline

    pid = next(
        p["id"] for p in client.get(API + "/execution/processes").json() if p["code"] == "L3-032"
    )
    project = client.post(
        API + "/projects",
        json={
            "name": "M8用途" + uuid4().hex[:6],
            "methodology": "BPI",
            "owner": "测试",
            "process_id": pid,
        },
    ).json()
    reviewer = next(
        u["id"] for u in client.get(API + "/auth/users").json() if u["username"] == "manager"
    )
    with SessionLocal() as db:
        model = ensure_baseline(db, db.get(ProcessArch, pid))
        if model.published_at is None:
            model.frozen_at = utcnow()
        row = ProcessImprovementRound(
            process_id=pid,
            project_id=project["id"],
            name="本轮",
            scope_note="测试",
            asis_model_version_id=model.id,
            baseline_confirmed_at=utcnow(),
            metric_contracts=[{"kpi_id": 1, "hash": "a" * 64}],
            baseline_samples=[{"record_id": 1, "value": 2}],
            acceptance_snapshot={
                "reviewer_user_id": reviewer,
                "target": "目标",
                "red_lines": "红线",
                "observation_rule": "观察",
            },
            revision=1,
        )
        db.add(row)
        db.commit()
        rid = row.id
    yield pid, project["id"], rid, reviewer
    with SessionLocal() as db:
        db.execute(delete(GateAttestation).where(GateAttestation.project_id == project["id"]))
        db.execute(delete(ProcessImprovementRound).where(ProcessImprovementRound.id == rid))
        db.commit()
    assert client.delete(API + f"/projects/{project['id']}").status_code == 200


def test_round_outcome_cannot_be_forged_through_normal_gate(client, outcome_scope):
    _, pid, _, _ = outcome_scope
    forged = client.post(
        API + "/maturity/gates",
        json={
            "project_id": pid,
            "stage_no": 1,
            "conclusion": "PASS",
            "evidence_url": "test://not-a-round",
            "purpose": "IMPROVEMENT_MET",
            "round_id": 999999,
            "expected_revision": 1,
        },
    )
    assert forged.status_code == 404, forged.text
    assert client.get(API + f"/maturity/gates?project_id={pid}").json() == []


def test_outcome_only_designated_independent_person_and_not_stage_progress(
    client, manager_client, outcome_scope
):
    process_id, pid, rid, _ = outcome_scope
    payload = {
        "project_id": pid,
        "stage_no": 1,
        "conclusion": "PASS",
        "evidence_url": "test://basis",
        "purpose": "DATA_READY",
        "round_id": rid,
        "expected_revision": 1,
    }
    assert client.post(API + "/maturity/gates", json=payload).status_code == 403
    accepted = manager_client.post(API + "/maturity/gates", json=payload)
    assert accepted.status_code == 201, accepted.text
    data = accepted.json()
    assert data["purpose"] == "DATA_READY" and data["round_id"] == rid
    assert data["evidence_snapshot"]["round_revision"] == 1
    rounds = client.get(API + f"/processes/{process_id}/improvement-rounds").json()
    result = next(r for r in rounds if r["id"] == rid)
    assert result["verification"][0]["state"] == "CONFIRMED"
    from app.core.database import SessionLocal
    from app.models.project import Project
    from app.services.maturity import latest_gate

    with SessionLocal() as db:
        assert latest_gate(db, pid, 1) is None
        assert db.get(Project, pid).current_stage == 1
    replay = manager_client.post(API + "/maturity/gates", json={**payload, "expected_revision": 0})
    assert replay.status_code == 409


def test_training_attendance_not_operation_and_wrong_model_rejected(
    client, manager_client, outcome_scope
):
    process_id, _, rid, reviewer = outcome_scope
    me = client.get(API + "/auth/me").json()["id"]
    response = client.post(
        API + "/pilot/training",
        json={
            "process_id": process_id,
            "trainee_user_id": me,
            "topic": "原培训",
            "completed_on": "2026-11-04",
        },
    )
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    try:
        records = client.get(API + f"/pilot/training?process_id={process_id}")
        assert records.status_code == 200, records.text
        original = next(r for r in records.json() if r["id"] == ident)
        assert original["operation_verified"] is False
        bad = client.put(
            API + f"/pilot/training/{ident}/operation",
            json={
                "expected_revision": 0,
                "round_id": rid,
                "model_version_id": 999999,
                "reviewer_user_id": reviewer,
                "scenario": "按原作业正常/异常演练",
                "evidence": "实际操作结果",
                "review_due": "2026-12-01",
            },
        )
        assert bad.status_code == 400, bad.text
        from app.core.database import SessionLocal
        from app.models.improvement_round import ProcessImprovementRound

        with SessionLocal() as db:
            vid = db.get(ProcessImprovementRound, rid).asis_model_version_id
        saved = client.put(
            API + f"/pilot/training/{ident}/operation",
            json={
                "expected_revision": 0,
                "round_id": rid,
                "model_version_id": vid,
                "reviewer_user_id": reviewer,
                "scenario": "正常及失败恢复",
                "evidence": "原操作记录",
                "review_due": "2026-12-01",
            },
        )
        assert saved.status_code == 200, saved.text
        accepted = manager_client.post(
            API + f"/pilot/training/{ident}/operation/review",
            json={
                "expected_revision": 1,
                "decision": "ACCEPT",
                "evidence": "本人观察办理及失败恢复",
            },
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["operation_verified"] is True
        revised = client.put(
            API + f"/pilot/training/{ident}/operation",
            json={
                "expected_revision": 2,
                "round_id": rid,
                "model_version_id": vid,
                "reviewer_user_id": reviewer,
                "scenario": "新场景",
                "evidence": "新依据",
                "review_due": "2026-12-01",
            },
        )
        assert revised.status_code == 200, revised.text
        assert revised.json()["operation"]["history"][-1]["review"]["decision"] == "ACCEPT"
    finally:
        from app.core.database import SessionLocal
        from app.models.adoption import ProcessTrainingRecord

        with SessionLocal() as db:
            db.delete(db.get(ProcessTrainingRecord, ident))
            db.commit()


def test_pack_freezes_source_and_receipt_does_not_publish_locally(
    client, manager_client, outcome_scope
):
    process_id, pid, rid, reviewer = outcome_scope
    item = client.post(
        API + "/replication-packs",
        json={
            "source_project_id": pid,
            "round_id": rid,
            "title": "M8固定包",
            "conditions": "同类业务，须本地准备",
            "benefit_evidence": "未确认收益",
            "receiver_user_id": reviewer,
        },
    ).json()
    ident = item["id"]
    try:
        assert item["source_snapshot"]["round_id"] == rid
        before = item["source_snapshot"]
        result = client.patch(
            API + f"/replication-packs/{ident}",
            json={"status": "PUBLISHED", "expected_revision": 0},
        )
        assert result.status_code == 200, result.text
        receipt = manager_client.post(
            API + f"/replication-packs/{ident}/receipt",
            json={
                "expected_revision": 1,
                "decision": "ACCEPT",
                "evidence": "本人按本地范围核对，仍须验证",
                "target_process_id": process_id,
            },
        )
        assert receipt.status_code == 200, receipt.text
        assert receipt.json()["source_snapshot"] == before
        assert receipt.json()["receipt"]["decision"] == "ACCEPT"
        assert "准备" in receipt.json()["receipt_label"]
        downgrade = client.patch(
            API + f"/replication-packs/{ident}", json={"status": "DRAFT", "expected_revision": 2}
        )
        assert downgrade.status_code == 409, downgrade.text
    finally:
        from app.core.database import SessionLocal
        from app.models.replication import ReplicationPack

        with SessionLocal() as db:
            db.delete(db.get(ReplicationPack, ident))
            db.commit()


def test_guarantees_read_only_twenty_original_sources(client, outcome_scope):
    process_id, _, _, _ = outcome_scope
    from sqlalchemy import func, select

    from app.core.database import SessionLocal
    from app.models.pilot import PilotTask

    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(PilotTask))
    response = client.get(API + f"/processes/{process_id}/governance-evidence")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 20
    assert {x["code"] for x in items} >= {"SP-01", "OW-04", "ST-03", "PF-03", "CU-04"}
    assert all(x["state"] in ("MISSING", "PENDING", "CONFIRMED", "STALE") for x in items)
    assert all("next_action" in x and "sources" in x for x in items)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PilotTask)) == before


def test_control_review_uses_original_sheet_and_has_next_owner(
    client, manager_client, outcome_scope
):
    process_id, _, rid, reviewer = outcome_scope
    created = client.post(
        API + f"/processes/{process_id}/control-reviews",
        json={
            "round_id": rid,
            "reviewer_user_id": reviewer,
            "owner_user_id": client.get(API + "/auth/me").json()["id"],
            "review_due": "2026-12-01",
            "evidence": "原绩效及异常回查",
            "decision": "维持并复核",
            "next_action": "按下一周期核对客户结果",
        },
    )
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["tool_code"] == "PDCA"
    reviewed = manager_client.post(
        API + f"/processes/{process_id}/control-reviews/{data['id']}/review",
        json={
            "expected_revision": 0,
            "decision": "ACCEPT",
            "evidence": "本人回查控制和下一责任期限",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review"]["decision"] == "ACCEPT"
    changed = manager_client.post(
        API + f"/processes/{process_id}/control-reviews/{data['id']}/review",
        json={"expected_revision": 1, "decision": "RETURN", "evidence": "追加异议原决定保留"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["work_context"]["review_history"][-1]["decision"] == "ACCEPT"
    from app.core.database import SessionLocal
    from app.models.tool_sheet import ToolSheet

    with SessionLocal() as db:
        db.delete(db.get(ToolSheet, data["id"]))
        db.commit()


def test_go_live_outcome_requires_same_current_publish_and_stales_with_config(
    client, manager_client, gate_case, outcome_scope
):
    from test_publish_gate_bindings import add_a, publish

    from app.core.database import SessionLocal
    from app.models.execution import ProcessExecutionConfig
    from app.models.improvement_round import ProcessImprovementRound
    from app.models.process import ProcessArch
    from app.models.project import Project
    from app.services.binding_readiness import binding_gate
    from app.services.execution_readiness import basis
    from app.services.improvement_round import digest

    add_a(client, gate_case)
    publish(client, gate_case)
    _original_process_id, pid, rid, _ = outcome_scope
    process_id = gate_case["pid"]
    with SessionLocal() as db:
        db.get(Project, pid).process_id = process_id
        original_round = db.get(ProcessImprovementRound, rid)
        original_round.process_id = process_id
        original_round.asis_model_version_id = gate_case["vid"]
        process = db.get(ProcessArch, process_id)
        version, _, snapshot, *_ = basis(db, process)
        row = db.get(ProcessImprovementRound, rid)
        row.released_model_version_id = version.id if version else row.asis_model_version_id
        if version is None:
            from app.models.process import ProcessModelVersion

            version = db.get(ProcessModelVersion, row.asis_model_version_id)
            version.status = "PUBLISHED"
            from app.core.timeutil import utcnow

            version.published_at = utcnow()
            process.published_model_version = version.version
            db.flush()
            snapshot = basis(db, process)[2]
        cfg = db.query(ProcessExecutionConfig).filter_by(process_id=process_id).first()
        if cfg is None:
            cfg = ProcessExecutionConfig(process_id=process_id)
            db.add(cfg)
        before = cfg.readiness
        old_due = cfg.default_task_due_hours
        db.flush()
        snapshot = basis(db, process)[2]
        cfg.readiness = {
            "requirements": {
                k: {"mode": "NOT_APPLICABLE", "reason": "测试人工办理"}
                for k in ("forms", "assignments", "deadlines")
            },
            "confirmation": {
                "decision": "ACCEPT",
                "fingerprint": digest(
                    {
                        **snapshot,
                        "binding_fingerprint": binding_gate(
                            db, process_id, profile="EXECUTION", model_version_id=version.id
                        ).fingerprint,
                    }
                ),
            },
        }
        db.commit()
    payload = {
        "project_id": pid,
        "stage_no": 1,
        "conclusion": "PASS",
        "purpose": "GO_LIVE_READY",
        "round_id": rid,
        "expected_revision": 1,
        "evidence_url": "test://current",
    }
    try:
        accepted = manager_client.post(API + "/maturity/gates", json=payload)
        assert accepted.status_code == 201, accepted.text
        with SessionLocal() as db:
            cfg = db.query(ProcessExecutionConfig).filter_by(process_id=process_id).one()
            data = dict(cfg.readiness)
            data.pop("confirmation")
            cfg.readiness = data
            db.commit()
        withdrawn = client.get(API + f"/processes/{process_id}/improvement-rounds/{rid}").json()
        assert (
            next(v for v in withdrawn["verification"] if v["key"] == "GO_LIVE_READY")["state"]
            != "CONFIRMED"
        )
        client.put(
            API + f"/execution/config?process_id={process_id}", json={"default_task_due_hours": 7}
        )
        row = client.get(API + f"/processes/{process_id}/improvement-rounds/{rid}").json()
        assert (
            next(v for v in row["verification"] if v["key"] == "GO_LIVE_READY")["state"]
            != "CONFIRMED"
        )
    finally:
        with SessionLocal() as db:
            cfg = db.query(ProcessExecutionConfig).filter_by(process_id=process_id).one()
            cfg.readiness = before
            cfg.default_task_due_hours = old_due
            db.commit()


def test_control_old_read_and_copy_get_preserve_source_scope(client, owner_client, outcome_scope):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.org import OrgUnit
    from app.models.project import Project
    from app.models.replication import ReplicationPack
    from app.models.tool_sheet import ToolSheet
    from app.models.user import User
    from app.services.org_access import subtree_ids

    process_id, pid, rid, reviewer = outcome_scope
    with SessionLocal() as db:
        user = db.get(User, owner_client.get(API + "/auth/me").json()["id"])
        outside = next(
            o.id
            for o in db.scalars(select(OrgUnit)).all()
            if o.id not in subtree_ids(db, user.org_unit_id)
        )
        db.get(Project, pid).org_unit_id = outside
        db.commit()
    control = client.post(
        API + f"/processes/{process_id}/control-reviews",
        json={
            "round_id": rid,
            "reviewer_user_id": reviewer,
            "owner_user_id": 1,
            "review_due": "2026-12-01",
            "evidence": "私有依据",
            "decision": "私有决定",
            "next_action": "私有行动",
        },
    ).json()
    pack = client.post(
        API + "/replication-packs",
        json={
            "source_project_id": pid,
            "round_id": rid,
            "title": "受限包",
            "conditions": "受限范围",
        },
    ).json()
    try:
        assert owner_client.get(API + f"/tools/PDCA/sheets/{control['id']}").status_code == 404
        assert owner_client.get(API + f"/replication-packs/{pack['id']}").status_code == 404
        assert pack["id"] not in {
            r["id"] for r in owner_client.get(API + "/replication-packs").json()
        }
    finally:
        with SessionLocal() as db:
            db.delete(db.get(ToolSheet, control["id"]))
            db.delete(db.get(ReplicationPack, pack["id"]))
            db.commit()


def test_no_runtime_outcome_without_published_and_formal_samples(manager_client, outcome_scope):
    _, pid, rid, _ = outcome_scope
    result = manager_client.post(
        API + "/maturity/gates",
        json={
            "project_id": pid,
            "stage_no": 1,
            "conclusion": "PASS",
            "evidence_url": "test://missing",
            "purpose": "RUN_EFFECTIVE",
            "round_id": rid,
            "expected_revision": 1,
        },
    )
    assert result.status_code == 400, result.text
