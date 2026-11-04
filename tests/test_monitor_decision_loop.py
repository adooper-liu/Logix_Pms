"""M7显式测量契约；时间单位不能替代取数语义。"""

from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def measurement_kpi(client):
    from sqlalchemy import delete

    from app.core.database import SessionLocal
    from app.models.monitor import KpiDefinition, KpiRecord

    ids = []

    def create(**extra):
        pid = next(
            p["id"]
            for p in client.get(API + "/execution/processes").json()
            if p["code"] == "L3-032"
        )
        payload = {
            "code": "M7-" + uuid4().hex[:8],
            "name": "显式测量" + uuid4().hex[:5],
            "dimension": "EFFICIENCY",
            "unit": "小时",
            "process_id": pid,
            "formula": "实例完成到开始历时的月均值",
            "frequency": "MONTHLY",
        }
        payload.update(extra)
        response = client.post(API + "/monitor/kpis", json=payload)
        if response.status_code == 201:
            ids.append(response.json()["id"])
        return response

    yield create
    with SessionLocal() as db:
        db.execute(delete(KpiRecord).where(KpiRecord.kpi_id.in_(ids)))
        db.execute(delete(KpiDefinition).where(KpiDefinition.id.in_(ids)))
        db.commit()


def elapsed_measurement():
    return {
        "source_kind": "EXECUTION_ELAPSED",
        "event": "instance.completed",
        "aggregation": "MEAN",
        "timezone": "UTC",
        "calendar": "ELAPSED",
        "minimum_samples": 3,
        "freshness_days": 45,
        "purpose": "核对客户端到端周期",
        "response_note": "数据责任人核对异常后决定是否分析",
    }


def test_time_unit_without_measurement_does_not_choose_execution(measurement_kpi):
    response = measurement_kpi()
    assert response.status_code == 201, response.text
    assert response.json()["intake"] == "DRAFT"
    assert response.json()["measurement"] is None


def test_explicit_elapsed_contract_is_saved_and_versioned(client, measurement_kpi):
    contract = elapsed_measurement()
    response = measurement_kpi(measurement=contract)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["measurement"] == contract
    assert data["intake"] == "EXECUTION"
    changed = client.patch(
        API + f"/monitor/kpis/{data['id']}",
        json={"measurement": {**contract, "minimum_samples": 5}},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert changed.json()["measurement"]["minimum_samples"] == 5


def test_completed_instances_only_populate_explicit_kpi_with_identity(client, measurement_kpi):
    from datetime import datetime, timedelta

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.execution import ProcessInstance
    from app.models.monitor import KpiDefinition, KpiRecord
    from app.services.kpi import record_completed_instance

    explicit = measurement_kpi(measurement={**elapsed_measurement(), "minimum_samples": 1}).json()
    unbound = measurement_kpi().json()
    with SessionLocal() as db:
        kpi = db.get(KpiDefinition, explicit["id"])
        now = datetime(2026, 11, 4, 12)
        instance = ProcessInstance(
            code="M7-" + uuid4().hex[:12],
            process_id=kpi.process_id,
            process_name="样本",
            status="COMPLETED",
            started_at=now - timedelta(hours=2),
            completed_at=now,
            definition_version=1,
            snapshot={},
            variables={},
        )
        db.add(instance)
        db.flush()
        try:
            record_completed_instance(db, instance)
            assert not db.scalars(select(KpiRecord).where(KpiRecord.kpi_id == unbound["id"])).all()
            record = db.scalar(select(KpiRecord).where(KpiRecord.kpi_id == kpi.id))
            assert record.value == 2
            assert record.provenance["instance_ids"] == [instance.id]
            assert record.provenance["quality"] == "UNKNOWN_IDENTITY"
        finally:
            db.rollback()


def test_manual_record_cannot_become_green_by_configuring_hook(client, measurement_kpi):
    data = measurement_kpi(
        measurement=elapsed_measurement(), red_threshold=8, yellow_threshold=6, green_threshold=4
    ).json()
    created = client.post(
        API + f"/monitor/kpis/{data['id']}/records",
        json={"period": "2026-11-01", "value": 0, "note": "人工零值"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["provenance"]["source_kind"] == "MANUAL"
    detail = client.get(API + f"/monitor/kpis/{data['id']}").json()
    assert detail["status"] == "GRAY"
    assert detail["quality"] != "VALID"
    assert detail["achievement_rate"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"event": "task.wait"},
        {"aggregation": "P95"},
        {"calendar": "WORKING"},
        {"timezone": "Asia/Shanghai"},
    ],
)
def test_unsupported_execution_measurement_is_rejected(measurement_kpi, change):
    response = measurement_kpi(measurement={**elapsed_measurement(), **change})
    assert response.status_code == 400, response.text


def test_exception_close_requires_action_review(client, owner_client):
    created = client.post(
        API + "/monitor/exceptions",
        json={"title": "M7处置核验", "owner_user_id": client.get(API + "/auth/me").json()["id"]},
    )
    assert created.status_code == 201, created.text
    ident = created.json()["id"]
    try:
        blocked = client.patch(API + f"/monitor/exceptions/{ident}", json={"status": "CLOSED"})
        assert blocked.status_code == 400, blocked.text
        reviewer = next(
            u["id"] for u in client.get(API + "/auth/users").json() if u["username"] == "chen"
        )
        saved = client.patch(
            API + f"/monitor/exceptions/{ident}",
            json={
                "expected_revision": 0,
                "status": "RESOLVED",
                "action_taken": "调整原配置",
                "resolution": {
                    "reviewer_user_id": reviewer,
                    "decision": "执行措施后核验",
                    "action_ref": "原配置变更记录",
                    "evidence": "执行前后原记录",
                    "expected_result": "异常不再复发",
                    "review_due": "2026-12-01",
                },
            },
        )
        assert saved.status_code == 200, saved.text
        payload = {
            "expected_revision": saved.json()["revision"],
            "decision": "ACCEPT",
            "evidence": "本人核对原结果",
            "result": "已验证预期实现",
        }
        assert (
            client.post(API + f"/monitor/exceptions/{ident}/review", json=payload).status_code
            == 403
        )
        reviewed = owner_client.post(API + f"/monitor/exceptions/{ident}/review", json=payload)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["status"] == "CLOSED"
        assert (
            owner_client.post(API + f"/monitor/exceptions/{ident}/review", json=payload).status_code
            == 409
        )
        reopened = client.patch(
            API + f"/monitor/exceptions/{ident}",
            json={"expected_revision": reviewed.json()["revision"], "status": "OPEN"},
        )
        assert reopened.status_code == 200, reopened.text
        assert not reopened.json()["resolution"].get("review")
    finally:
        client.delete(API + f"/monitor/exceptions/{ident}")


def test_runtime_sample_retains_old_value_and_rejects_wrong_round_model(client, measurement_kpi):
    from datetime import datetime, timedelta
    from types import SimpleNamespace

    from fastapi import HTTPException
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.execution import ProcessInstance
    from app.models.monitor import KpiDefinition, KpiRecord
    from app.models.process import ProcessArch
    from app.schemas.improvement_round import SampleInput, Window
    from app.services import improvement_round
    from app.services import kpi as service

    data = measurement_kpi(measurement={**elapsed_measurement(), "minimum_samples": 1}).json()
    with SessionLocal() as db:
        kpi = db.get(KpiDefinition, data["id"])
        process = db.get(ProcessArch, kpi.process_id)
        from app.services.execution_readiness import published
        from app.services.process_model import ensure_baseline

        version = published(db, process) or ensure_baseline(db, process)
        now = datetime(2026, 11, 4)
        instance = ProcessInstance(
            code="M7-" + uuid4().hex[:12],
            process_id=kpi.process_id,
            process_name="正式身份",
            status="COMPLETED",
            started_at=now - timedelta(hours=2),
            completed_at=now,
            model_version_id=version.id,
            definition_version=version.version,
            snapshot={},
            variables={},
        )
        db.add(instance)
        db.flush()
        try:
            service.record_completed_instance(db, instance)
            record = db.scalar(select(KpiRecord).where(KpiRecord.kpi_id == kpi.id))
            assert record.provenance["model_version_id"] == version.id
            sample = SampleInput(
                record_id=record.id,
                source_evidence="原实例",
                quality_note="核对",
                contract_hash="a" * 64,
            )
            row = SimpleNamespace(
                id=999, process_id=kpi.process_id, project_id=None, baseline_samples=[]
            )
            with pytest.raises(HTTPException) as exc:
                improvement_round.samples(
                    db,
                    db.get(__import__("app.models.user", fromlist=["User"]).User, 1),
                    row,
                    [sample],
                    Window(start="2026-11-01", end="2026-11-30"),
                    "AFTER",
                    version.id + 100,
                    [{"kpi_id": kpi.id, "hash": "a" * 64, "measurement": kpi.measurement}],
                )
            assert exc.value.status_code == 400
            # 当前取分钟不得套用旧小时契约。
            frozen = {
                key: getattr(kpi, key)
                for key in (
                    "measurement",
                    "formula",
                    "unit",
                    "process_id",
                    "activity_id",
                    "frequency",
                )
            }
            frozen.update(kpi_id=kpi.id, hash="a" * 64)
            kpi.unit = "分钟"
            db.flush()
            service.record_completed_instance(db, instance)
            sample_before = sample.model_copy(update={"contract_hash": None})
            with pytest.raises(HTTPException):
                improvement_round.samples(
                    db,
                    db.get(__import__("app.models.user", fromlist=["User"]).User, 1),
                    row,
                    [sample_before],
                    Window(start="2026-11-01", end="2026-11-30"),
                    "BASELINE",
                    version.id,
                    [frozen],
                )
            service.record_completed_instance(db, instance)
            assert record.revision >= 1
        finally:
            db.rollback()


def test_action_edit_updates_editor_and_reopens_closed_result(client, manager_client):
    from app.core.database import SessionLocal
    from app.models.monitor import ExceptionEvent

    admin = client.get(API + "/auth/me").json()["id"]
    reviewer = manager_client.get(API + "/auth/me").json()["id"]
    event = client.post(
        API + "/monitor/exceptions", json={"title": "核验独立性", "owner_user_id": admin}
    ).json()
    eid = event["id"]
    try:
        with SessionLocal() as db:
            row = db.get(ExceptionEvent, eid)
            row.status = "RESOLVED"
            row.action_taken = "原措施"
            row.resolution = {
                "reviewer_user_id": reviewer,
                "edited_by_id": admin,
                "review": {"decision": "ACCEPT"},
            }
            db.commit()
        changed = manager_client.patch(
            API + f"/monitor/exceptions/{eid}",
            json={"expected_revision": 0, "action_taken": "核验人改的措施"},
        )
        assert changed.status_code == 200, changed.text
        refused = manager_client.post(
            API + f"/monitor/exceptions/{eid}/review",
            json={
                "expected_revision": 1,
                "decision": "ACCEPT",
                "evidence": "自验",
                "result": "自验",
            },
        )
        assert refused.status_code == 403, refused.text
        with SessionLocal() as db:
            row = db.get(ExceptionEvent, eid)
            row.status = "CLOSED"
            from app.core.timeutil import utcnow

            row.closed_at = utcnow()
            row.resolution = {
                "edited_by_id": admin,
                "reviewer_user_id": reviewer,
                "review": {"decision": "ACCEPT"},
            }
            db.commit()
        changed = client.patch(
            API + f"/monitor/exceptions/{eid}",
            json={"expected_revision": 1, "action_taken": "关闭后改措施"},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["status"] != "CLOSED"
        assert changed.json()["closed_at"] is None
    finally:
        client.delete(API + f"/monitor/exceptions/{eid}")


def test_measurement_audit_keeps_before_and_after(client, measurement_kpi):
    import json

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.user import AuditLog

    item = measurement_kpi(measurement=elapsed_measurement()).json()
    response = client.patch(
        API + f"/monitor/kpis/{item['id']}",
        json={"measurement": {**elapsed_measurement(), "minimum_samples": 5}},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        log = db.scalar(
            select(AuditLog)
            .where(
                AuditLog.entity_type == "kpi",
                AuditLog.entity_id == item["id"],
                AuditLog.action == "UPDATE",
            )
            .order_by(AuditLog.id.desc())
        )
        snapshot = json.loads(log.summary)
        assert snapshot["before"]["measurement"]["minimum_samples"] == 3
        assert snapshot["after"]["measurement"]["minimum_samples"] == 5


def test_exception_source_project_visibility_is_preserved(client, owner_client):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.execution import ProcessInstance
    from app.models.org import OrgUnit
    from app.models.project import Project
    from app.models.user import User
    from app.services.org_access import subtree_ids

    user = owner_client.get(API + "/auth/me").json()
    with SessionLocal() as db:
        owner = db.get(User, user["id"])
        outside = next(
            o
            for o in db.scalars(select(OrgUnit)).all()
            if o.id not in subtree_ids(db, owner.org_unit_id)
        )
        project = Project(
            code="M7-P-" + uuid4().hex[:8],
            name="受限项目",
            methodology="BPI",
            owner="测试",
            org_unit_id=outside.id,
        )
        db.add(project)
        db.flush()
        instance = ProcessInstance(
            code="M7-I-" + uuid4().hex[:8],
            project_id=project.id,
            process_name="受限",
            status="COMPLETED",
            snapshot={},
            variables={},
        )
        db.add(instance)
        db.commit()
        iid = instance.id
        project_id = project.id
    event = client.post(
        API + "/monitor/exceptions", json={"title": "来源私有详情", "source_instance_id": iid}
    ).json()
    eid = event["id"]
    try:
        assert owner_client.get(API + f"/monitor/exceptions/{eid}").status_code == 404
        assert eid not in {e["id"] for e in owner_client.get(API + "/monitor/exceptions").json()}
    finally:
        client.delete(API + f"/monitor/exceptions/{eid}")
        with SessionLocal() as db:
            db.delete(db.get(ProcessInstance, iid))
            db.flush()
            db.delete(db.get(Project, project_id))
            db.commit()


def test_elapsed_measurement_requires_duration_and_monthly_scope(measurement_kpi):
    assert measurement_kpi(measurement=elapsed_measurement(), unit="%").status_code == 400
    assert measurement_kpi(measurement=elapsed_measurement(), frequency="WEEKLY").status_code == 400
