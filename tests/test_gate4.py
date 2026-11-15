"""Gate 4: configuration is not approval, and routing cannot bypass controls."""

from copy import deepcopy

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from app.services import forms


@pytest.mark.parametrize("approved,target", [("是", "n5"), ("否", "n6")])
def test_controlled_branch_accepts_only_matching_target(approved, target):
    edges = [
        {"dst": "n5", "match_conditions": [{"field": "approved", "op": "eq", "value": "是"}]},
        {"dst": "n6", "match_conditions": [{"field": "approved", "op": "eq", "value": "否"}]},
    ]
    assert forms.resolve_target(edges, [], {"approved": approved}) == target
    assert forms.resolve_target(edges, [], {"approved": approved}, target) == target
    wrong = "n6" if target == "n5" else "n5"
    with pytest.raises(HTTPException):
        forms.resolve_target(edges, [], {"approved": approved}, wrong)


def test_conditional_single_edge_does_not_fall_through():
    edges = [{"dst": "n2", "match_conditions": [{"field": "ready", "op": "eq", "value": "是"}]}]
    for explicit in (None, "n2"):
        with pytest.raises(HTTPException):
            forms.resolve_target(edges, [], {"ready": "否"}, explicit)
    assert forms.resolve_target(edges, [], {"ready": "是"}) == "n2"


def test_unconditional_and_legacy_routing_remains_available():
    assert forms.resolve_target([{"dst": "n2"}], [], {}) == "n2"
    assert forms.resolve_target([{"dst": "n2"}, {"dst": "n3"}], [], {}, "n3") == "n3"
    assert forms.resolve_target([], [], {}) is None
    rules = [{"conditions": [{"field": "x", "op": "eq", "value": 1}], "target": "n3"}]
    assert forms.resolve_target([{"dst": "n2"}, {"dst": "n3"}], rules, {"x": 1}) == "n3"


def test_ambiguous_controlled_routes_are_rejected():
    condition = [{"field": "x", "op": "eq", "value": 1}]
    with pytest.raises(HTTPException):
        forms.resolve_target(
            [
                {"dst": "a", "match_conditions": condition},
                {"dst": "b", "match_conditions": condition},
            ],
            [],
            {"x": 1},
        )


@pytest.fixture
def gate4_db(client):
    from app.core.database import SessionLocal
    from app.models.process import ProcessArch, ProcessModelVersion
    from app.services.process_model import ensure_baseline

    with SessionLocal() as db:
        process = db.scalar(select(ProcessArch).where(ProcessArch.code == "L3-032"))
        baseline = ensure_baseline(db, process)
        dirty = deepcopy(baseline.snapshot)
        dirty["nodes"].append({"node_key": "test-only", "name": "测试污染", "node_type": "TASK"})
        db.add(
            ProcessModelVersion(
                process_id=process.id,
                version=baseline.version + 1,
                status="DRAFT",
                snapshot=dirty,
                change_note="保留的测试草稿",
            )
        )
        db.flush()
        yield db, process
        db.rollback()


def test_prepare_gate4_preserves_history_and_leaves_business_confirmation_open(gate4_db):
    from app.models.asset_graph import NodeActivityLink
    from app.models.execution import FormDefinition, NodeAssignment, ProcessInstance
    from app.models.process import ProcessModelVersion
    from app.models.process_document import ProcessDocumentVersion
    from app.models.resource_link import ActivityResourceLink
    from app.services import gate4_configuration as service
    from app.services.storage import get_storage

    db, process = gate4_db
    old_versions = [
        (v.id, deepcopy(v.snapshot), v.status)
        for v in db.scalars(
            select(ProcessModelVersion).where(ProcessModelVersion.process_id == process.id)
        )
    ]
    old_instances = [
        (i.id, deepcopy(i.snapshot), i.model_version_id)
        for i in db.scalars(select(ProcessInstance).where(ProcessInstance.process_id == process.id))
    ]
    assigned = db.scalar(select(func.count()).select_from(NodeAssignment))
    published = process.published_model_version
    result = service.prepare(db, "L3-032")
    version = db.get(ProcessModelVersion, result["model_version_id"])
    assert version.status == "DRAFT" and version.frozen_at is not None
    assert version.published_at is None and version.reviewed_at is None
    assert version.created_by_id is None
    assert len(version.snapshot["nodes"]) == 6
    assert "test-only" not in {n["node_key"] for n in version.snapshot["nodes"]}
    links = db.scalars(
        select(NodeActivityLink).where(NodeActivityLink.model_version_id == version.id)
    ).all()
    assert len(links) == 6
    assert all(link.confirmed_at is None and link.confirmed_by_id is None for link in links)
    active_forms = db.scalars(
        select(FormDefinition).where(
            FormDefinition.process_id == process.id, FormDefinition.is_active.is_(True)
        )
    ).all()
    assert {f.node_key for f in active_forms} == {"n1", "n2", "n3", "n4", "n5", "n6"}
    resources = db.scalars(
        select(ActivityResourceLink).where(
            ActivityResourceLink.activity_id.in_([link.activity_id for link in links]),
            ActivityResourceLink.resource_type == "FORM",
            ActivityResourceLink.is_active.is_(True),
        )
    ).all()
    assert len(resources) == 6
    doc_version = db.get(ProcessDocumentVersion, result["document_version_id"])
    assert doc_version.status == "DRAFT" and doc_version.approved_at is None
    with get_storage().open(doc_version.storage_key) as f:
        content = f.read().decode("utf-8")
    assert "时限" in content and "升级" in content and "未验证" in content
    assert process.published_model_version == published
    assert db.scalar(select(func.count()).select_from(NodeAssignment)) == assigned
    for ident, snapshot, status in old_versions:
        original = db.get(ProcessModelVersion, ident)
        assert original.snapshot == snapshot and original.status == status
    assert [
        (i.id, i.snapshot, i.model_version_id)
        for i in db.scalars(select(ProcessInstance).where(ProcessInstance.process_id == process.id))
    ] == old_instances
    assert service.check(db, "L3-032")["configuration_ready"] is True
    again = service.prepare(db, "L3-032")
    assert again["model_version_id"] == version.id
    assert again["document_version_id"] == doc_version.id


def test_prepared_routes_require_budget_and_rework_records(gate4_db):
    from app.models.execution import FormDefinition
    from app.models.process import ProcessModelVersion
    from app.services import gate4_configuration as service

    db, process = gate4_db
    result = service.prepare(db, "L3-032")
    version = db.get(ProcessModelVersion, result["model_version_id"])

    def outgoing(key):
        return [
            {**e, "dst": e["target_key"]}
            for e in version.snapshot["edges"]
            if e["source_key"] == key
        ]

    assert forms.resolve_target(outgoing("n3"), [], {"budget_ok": "是"}) == "n4"
    assert forms.resolve_target(outgoing("n3"), [], {"budget_ok": "否"}) == "n6"
    with pytest.raises(HTTPException):
        forms.resolve_target(outgoing("n3"), [], {"budget_ok": "否"}, "n4")
    with pytest.raises(HTTPException):
        forms.resolve_target(outgoing("n6"), [], {"resubmit_ready": "否"})
    assert forms.resolve_target(outgoing("n6"), [], {"resubmit_ready": "是"}) == "n2"
    for form in db.scalars(select(FormDefinition).where(FormDefinition.process_id == process.id)):
        if form.is_active:
            with pytest.raises(HTTPException):
                forms.validate_form_data(form.fields, {})


def test_prepare_refuses_to_overwrite_later_manual_changes(gate4_db):
    from app.models.execution import FormDefinition
    from app.services import gate4_configuration as service

    db, process = gate4_db
    service.prepare(db, "L3-032")
    form = db.scalar(
        select(FormDefinition).where(
            FormDefinition.process_id == process.id, FormDefinition.node_key == "n3"
        )
    )
    form.fields = []
    db.flush()
    with pytest.raises(ValueError, match="变化"):
        service.prepare(db, "L3-032")
    assert form.fields == []


def test_preview_rolls_back_without_storing_files(gate4_db):
    from app.models.process import ProcessModelVersion
    from app.models.process_document import ProcessDocument
    from app.services import gate4_configuration as service
    from app.services.storage import get_storage

    db, _process = gate4_db
    before = db.scalar(select(func.count()).select_from(ProcessModelVersion))
    files_before = set(get_storage().root.rglob("*"))
    with db.begin_nested() as savepoint:
        result = service.prepare(db, "L3-032", persist_file=False)
        assert result["preview"] is True
        document = db.scalar(
            select(ProcessDocument).where(ProcessDocument.code == "PD-L3-032-GATE4")
        )
        assert document is not None
        assert set(get_storage().root.rglob("*")) == files_before
        savepoint.rollback()
    assert db.scalar(select(func.count()).select_from(ProcessModelVersion)) == before
    assert service.check(db, "L3-032")["configuration_ready"] is False


def test_task_completion_cannot_bypass_conditions(client):
    pid = next(
        row["id"]
        for row in client.get("/api/v1/execution/processes").json()
        if row["code"] == "L3-032"
    )
    response = client.post("/api/v1/execution/instances", json={"process_id": pid})
    assert response.status_code == 201, response.text
    iid = response.json()["id"]
    try:
        for step in range(3):
            task = client.get(
                "/api/v1/execution/tasks", params={"instance_id": iid, "only_open": True}
            ).json()[0]
            data = {"applicant": "隔离验证", "amount": 100} if step == 0 else {}
            done = client.post(
                f"/api/v1/execution/tasks/{task['id']}/complete", json={"form_data": data}
            )
            assert done.status_code == 200, done.text
        task = client.get(
            "/api/v1/execution/tasks", params={"instance_id": iid, "only_open": True}
        ).json()[0]
        rejected = client.post(
            f"/api/v1/execution/tasks/{task['id']}/complete",
            json={"form_data": {"approved": "否"}, "next_node_key": "n5"},
        )
        assert rejected.status_code == 400, rejected.text
        again = client.get(f"/api/v1/execution/tasks/{task['id']}").json()
        assert again["status"] in {"PENDING", "CLAIMED"}
    finally:
        client.delete(f"/api/v1/execution/instances/{iid}")


def test_default_flag_cannot_bypass_its_own_condition():
    edge = {
        "dst": "next",
        "match_conditions": [{"field": "ready", "op": "eq", "value": "yes"}],
        "is_default": True,
    }
    for explicit in (None, "next"):
        with pytest.raises(HTTPException):
            forms.resolve_target([edge], [], {"ready": "no"}, explicit)


def test_frozen_bindings_match_completed_configuration(gate4_db):
    from app.models.process import ProcessModelVersion
    from app.services import binding_snapshot
    from app.services import gate4_configuration as service

    db, process = gate4_db
    result = service.prepare(db)
    version = db.get(ProcessModelVersion, result["model_version_id"])
    current = binding_snapshot.capture(db, process, version)
    assert current["activities"] == version.binding_snapshot["activities"]


def test_inactive_carrier_link_is_not_reported_ready(gate4_db):
    from app.models.execution import FormDefinition
    from app.models.process import ProcessArch
    from app.models.resource_link import ActivityResourceLink
    from app.services import gate4_configuration as service

    db, process = gate4_db
    form = db.scalar(
        select(FormDefinition).where(
            FormDefinition.process_id == process.id, FormDefinition.node_key == "n1"
        )
    )
    activity_id = db.scalar(
        select(ProcessArch.id).where(
            ProcessArch.parent_id == process.id, ProcessArch.code == "L4-201"
        )
    )
    db.add(
        ActivityResourceLink(
            activity_id=activity_id,
            resource_type="FORM",
            ref_id=form.id,
            ref_key=f"FORM:{form.id}",
            node_key="n1",
            is_active=False,
        )
    )
    db.flush()
    with pytest.raises(ValueError, match="停用"):
        service.prepare(db)


@pytest.mark.parametrize("edited", ["control_points", "exception_terms", "is_active", "bpmn_xml"])
def test_check_detects_document_or_xml_manual_changes(gate4_db, edited):
    from app.models.process import ProcessModelVersion
    from app.models.process_document import ProcessDocument
    from app.services import gate4_configuration as service

    db, _process = gate4_db
    result = service.prepare(db)
    if edited == "bpmn_xml":
        db.get(ProcessModelVersion, result["model_version_id"]).bpmn_xml = "changed"
    else:
        setattr(
            db.get(ProcessDocument, result["document_id"]),
            edited,
            False if edited == "is_active" else "changed",
        )
    db.flush()
    with pytest.raises(ValueError, match="变化"):
        service.check(db)


def test_rollback_removes_only_new_attachment(gate4_db):
    from app.services import gate4_configuration as service
    from app.services.storage import get_storage

    db, _process = gate4_db
    storage = get_storage()
    before = set(storage.root.rglob("*.txt"))
    service.prepare(db)
    assert set(storage.root.rglob("*.txt")) != before
    db.rollback()
    assert set(storage.root.rglob("*.txt")) == before


def test_invalid_process_does_not_partially_apply(gate4_db):
    from app.models.process import ProcessArch, ProcessModelVersion
    from app.services import gate4_configuration as service

    db, process = gate4_db
    activity = db.scalar(
        select(ProcessArch).where(ProcessArch.parent_id == process.id, ProcessArch.code == "L4-206")
    )
    activity.is_draft = True
    before = db.scalar(select(func.count()).select_from(ProcessModelVersion))
    with pytest.raises(ValueError):
        service.prepare(db, "L3-032")
    assert db.scalar(select(func.count()).select_from(ProcessModelVersion)) == before
