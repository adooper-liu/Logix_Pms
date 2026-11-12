"""P0 只读绑定：真实查询、身份隔离与不能洗绿的继承。"""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event

from app.core.database import SessionLocal, engine
from app.core.timeutil import utcnow
from app.models.asset_graph import NodeActivityLink
from app.models.execution import FormDefinition
from app.models.monitor import KpiDefinition
from app.models.org import Position
from app.models.process import ProcessArch, ProcessModelVersion, ProcessNode
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.raci import GovernanceRole, RaciAssignment
from app.models.workload import WorkMeasurementStandard

API = "/api/v1"


@pytest.fixture
def binding_case(client):
    """独立流程，最后回滚所有测试输入，不污染既有统计。"""
    with SessionLocal() as db:
        suffix = uuid4().hex[:8]
        process = ProcessArch(code=f"BP-{suffix}", name="绑定测试", level=3)
        db.add(process)
        db.flush()
        activity = ProcessArch(code=f"BA-{suffix}", name="测试活动", level=4, parent_id=process.id)
        other = ProcessArch(code=f"BO-{suffix}", name="另一流程", level=3)
        position = Position(code=f"POS-{suffix}", name="绑定岗位")
        db.add_all([activity, other, position])
        db.flush()
        node = ProcessNode(
            process_id=process.id,
            node_key="Task_A",
            name="当前活动",
            node_type="TASK",
            process_arch_id=activity.id,
            duration_minutes=0,
        )
        db.add(node)
        db.commit()
        yield db, process, activity, other, position, node
        # 外键对象按引用次序删除；不依赖 SQLite 关闭外键。
        db.rollback()
        for cls in (
            RaciAssignment,
            NodeActivityLink,
            FormDefinition,
            KpiDefinition,
            ProcessDocument,
            ProcessModelVersion,
            ProcessNode,
        ):
            for row in db.query(cls).filter_by(process_id=process.id).all():
                db.delete(row)
            db.flush()
        for row in db.query(WorkMeasurementStandard).filter_by(activity_id=activity.id).all():
            db.delete(row)
        db.flush()
        db.delete(position)
        db.delete(activity)
        db.flush()
        db.delete(process)
        db.delete(other)
        db.commit()


def _get(client, process):
    response = client.get(f"{API}/processes/{process.id}/binding-readiness")
    assert response.status_code == 200, response.text
    return response.json()


def _facet(data, key):
    return next(item for item in data["activities"][0]["facets"] if item["key"] == key)


def test_readiness_is_read_only_and_viewable(binding_case, client, viewer_client, anon_client):
    db, process, activity, _, _, _ = binding_case
    writes = []

    def capture(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split()[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        data = _get(viewer_client, process)
        again = _get(client, process)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not writes
    assert data == again
    assert data["activities"][0]["activity_id"] == activity.id
    assert {item["status"] for item in data["activities"][0]["facets"]} <= {"MISSING", "PARTIAL"}

    assert data["nodes"][0]["marker"] in {"red", "yellow"}

    assert data["summary"]["overall"] in {"MISSING", "PARTIAL"}

    assert data["model_version_id"] is None
    assert db.query(ProcessModelVersion).filter_by(process_id=process.id).count() == 0
    assert anon_client.get(f"{API}/processes/{process.id}/binding-readiness").status_code == 401
    assert client.get(f"{API}/processes/99999999/binding-readiness").status_code == 404
    assert (
        client.post(f"{API}/processes/{process.id}/binding-readiness", json={}).status_code == 405
    )


def test_company_design_visible_to_viewer_without_private_refs(binding_case, viewer_client):
    from app.models.org import OrgUnit

    db, process, _, _, position, node = binding_case
    org = OrgUnit(code=f"ORG-{process.code}", name="另一组织", type="DEPARTMENT", path="/private/")
    db.add(org)
    db.flush()
    process.org_unit_id = org.id
    position.org_unit_id = org.id
    node.owner_position_id = position.id
    db.commit()
    try:
        data = _get(viewer_client, process)
        assert not any(ref["kind"] == "POSITION" for ref in _facet(data, "TEAM")["refs"])
        assert "绑定岗位" not in str(data)
    finally:
        process.org_unit_id = None
        position.org_unit_id = None
        db.commit()
        db.delete(org)
        db.commit()


def test_goal_direct_inherited_and_zero_target(binding_case, client):
    db, process, activity, _, _, _ = binding_case
    kpi = KpiDefinition(
        code=f"K-{process.code}",
        name="周期",
        dimension="EFFICIENCY",
        process_id=process.id,
        direction="LOWER_BETTER",
        target_value=0,
        measurement={"source_kind": "EXECUTION_ELAPSED"},
    )
    db.add(kpi)
    db.commit()
    inherited = _facet(_get(client, process), "GOAL")
    assert inherited["status"] == "PARTIAL"
    assert inherited["source"] == "INHERITED"
    kpi.activity_id = activity.id
    db.commit()
    direct = _facet(_get(client, process), "GOAL")
    assert direct["status"] == "READY"
    assert direct["refs"][0]["id"] == kpi.id
    kpi.measurement = {}
    db.commit()
    assert _facet(_get(client, process), "GOAL")["status"] == "PARTIAL"
    kpi.is_active = False
    db.commit()
    assert _facet(_get(client, process), "GOAL")["status"] == "MISSING"


def test_position_and_process_raci_never_imply_activity_a(binding_case, client):
    db, process, _, _, position, node = binding_case
    node.owner_position_id = position.id
    db.commit()
    facet = _facet(_get(client, process), "TEAM")
    assert facet["status"] == "PARTIAL"
    assert any(ref["kind"] == "POSITION" for ref in facet["refs"])
    assert any("RACI" in gap for gap in facet["gaps"])
    role = GovernanceRole(code=f"R-{process.code}", name="事项负责人", is_active=True)
    db.add(role)
    db.flush()
    db.add(RaciAssignment(process_id=process.id, matter="测试活动", role_id=role.id, raci="A"))
    db.commit()
    try:
        facet = _facet(_get(client, process), "TEAM")
        assert facet["status"] == "PARTIAL"
        assert any(ref["source"] == "PROCESS" for ref in facet["refs"])
    finally:
        db.query(RaciAssignment).filter_by(role_id=role.id).delete()
        db.delete(role)
        db.commit()


def test_resource_estimate_default_and_verified_standard(binding_case, client):
    db, process, activity, _, position, node = binding_case
    node.duration_minutes = 12
    form = FormDefinition(process_id=process.id, node_key="", name="默认记录", fields=[])
    db.add(form)
    db.commit()
    facet = _facet(_get(client, process), "RESOURCE")
    assert facet["status"] == "PARTIAL"
    assert any(ref["kind"] == "DESIGN_ESTIMATE" for ref in facet["refs"])
    assert not any(ref["kind"] == "WORK_STANDARD" for ref in facet["refs"])
    form.node_key = node.node_key
    node.owner_position_id = position.id
    standard = WorkMeasurementStandard(
        code=f"W-{process.code}",
        name="验证工时",
        activity_id=activity.id,
        position_id=position.id,
        status="VERIFIED",
        standard_minutes=10,
    )
    db.add(standard)
    db.commit()
    facet = _facet(_get(client, process), "RESOURCE")
    assert facet["status"] == "READY"
    assert {ref["kind"] for ref in facet["refs"]} >= {"DESIGN_ESTIMATE", "WORK_STANDARD", "FORM"}
    standard.valid_to = utcnow().date() - timedelta(days=1)
    db.commit()
    assert _facet(_get(client, process), "RESOURCE")["status"] == "PARTIAL"


def test_method_effective_dates_and_inheritance(binding_case, client):
    db, process, _, _, _, node = binding_case
    document = ProcessDocument(
        process_id=process.id,
        code=f"D-{process.code}",
        title="作业标准",
        category="SOP",
        node_key=node.node_key,
        control_points="核对数量",
    )
    version = ProcessDocumentVersion(
        document=document,
        version_label="1.0",
        status="EFFECTIVE",
        valid_to=utcnow().date() - timedelta(days=1),
    )
    db.add(document)
    db.commit()
    assert _facet(_get(client, process), "METHOD")["status"] == "MISSING"
    version.valid_to = None
    db.commit()
    assert _facet(_get(client, process), "METHOD")["status"] == "READY"
    document.node_key = None
    db.commit()
    inherited = _facet(_get(client, process), "METHOD")
    assert inherited["status"] == "PARTIAL"
    assert inherited["source"] == "INHERITED"


def test_current_draft_and_version_mapping_precedence(binding_case, client):
    db, process, activity, _, _, node = binding_case
    old = ProcessModelVersion(
        process_id=process.id,
        version=1,
        status="PUBLISHED",
        snapshot={
            "nodes": [{"node_key": "Old", "name": "旧活动", "node_type": "TASK"}],
            "edges": [],
        },
    )
    current = ProcessModelVersion(
        process_id=process.id,
        version=2,
        status="DRAFT",
        snapshot={
            "nodes": [{"node_key": "New", "name": "新活动", "node_type": "TASK"}],
            "edges": [],
        },
    )
    db.add_all([old, current])
    db.flush()
    db.add_all(
        [
            NodeActivityLink(
                process_id=process.id,
                model_version_id=old.id,
                node_key="New",
                activity_id=activity.id,
                relation="REALIZES",
            ),
            NodeActivityLink(
                process_id=process.id,
                model_version_id=current.id,
                node_key="New",
                activity_id=activity.id,
                relation="PART_OF",
            ),
        ]
    )
    db.commit()
    data = _get(client, process)
    assert data["model_version_id"] == current.id
    assert [item["node_key"] for item in data["nodes"]] == ["New"]
    assert data["activities"][0]["node_keys"] == ["New"]
    assert data["nodes"][0]["activity_ids"] == [activity.id]
    assert not any(item["node_key"] == node.node_key for item in data["nodes"])


def test_method_control_and_evidence_references(binding_case, client):
    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget

    db, process, activity, _, _, node = binding_case
    document = ProcessDocument(
        process_id=process.id,
        code=f"EV-{process.code}",
        title="证据标准",
        category="SOP",
        node_key=node.node_key,
    )
    version = ProcessDocumentVersion(document=document, version_label="1.0", status="EFFECTIVE")
    db.add(document)
    db.flush()
    claim = EvidenceClaim(
        process_id=process.id,
        claim="活动控制要求",
        claim_type="CONTROL",
        source_type="DOCUMENT_VERSION",
        source_id=version.id,
        source_hash="a" * 64,
        source_version="1.0",
        method="DOCUMENTED",
        status="SUPPORTED",
        targets=[EvidenceClaimTarget(target_type="ACTIVITY", target_id=activity.id)],
    )
    db.add(claim)
    db.commit()
    try:
        facet = _facet(_get(client, process), "METHOD")
        assert facet["status"] == "READY"
        assert any(ref["kind"] == "EVIDENCE" and ref["id"] == claim.id for ref in facet["refs"])
        claim.valid_to = utcnow().date() - timedelta(days=1)
        db.commit()
        assert _facet(_get(client, process), "METHOD")["status"] == "PARTIAL"
        claim.valid_to = None
        claim.status = "CONFLICTED"
        db.commit()
        assert _facet(_get(client, process), "METHOD")["status"] == "CONFLICT"
    finally:
        db.delete(claim)
        db.commit()


def test_multinode_resource_requires_every_position_and_carrier(binding_case, client):
    db, process, activity, _, position, node = binding_case
    node.owner_position_id = position.id
    node2 = ProcessNode(
        process_id=process.id,
        node_key="Task_B",
        name="第二节点",
        node_type="TASK",
        process_arch_id=activity.id,
    )
    form = FormDefinition(process_id=process.id, node_key=node.node_key, name="记录A", fields=[])
    standard = WorkMeasurementStandard(
        code=f"MULTI-{process.code}",
        name="验证工时",
        activity_id=activity.id,
        position_id=position.id,
        status="VERIFIED",
        standard_minutes=10,
    )
    db.add_all([node2, form, standard])
    db.commit()
    assert _facet(_get(client, process), "RESOURCE")["status"] == "PARTIAL"
    form2 = FormDefinition(process_id=process.id, node_key=node2.node_key, name="记录B", fields=[])
    db.add(form2)
    db.commit()
    assert _facet(_get(client, process), "RESOURCE")["status"] == "PARTIAL"
    node2.owner_position_id = position.id
    db.commit()
    assert _facet(_get(client, process), "RESOURCE")["status"] == "READY"


def test_private_document_not_exposed_through_process_scope(binding_case, viewer_client):
    from app.models.org import OrgUnit

    db, process, _, _, _, node = binding_case
    org = OrgUnit(
        code=f"DOCORG-{process.code}", name="受限组织", type="DEPARTMENT", path="/private/"
    )
    db.add(org)
    db.flush()
    process.org_unit_id = org.id
    document = ProcessDocument(
        process_id=process.id,
        org_unit_id=org.id,
        code=f"PRIVATE-{process.code}",
        title="受限SOP内容",
        category="SOP",
        node_key=node.node_key,
        control_points="秘密控制",
    )
    document.versions = [ProcessDocumentVersion(version_label="1.0", status="EFFECTIVE")]
    db.add(document)
    db.commit()
    try:
        data = _get(viewer_client, process)
        assert "受限SOP内容" not in str(data)
        assert _facet(data, "METHOD")["status"] == "MISSING"
    finally:
        db.delete(document)
        process.org_unit_id = None
        db.commit()
        db.delete(org)
        db.commit()


def test_control_link_without_sop_still_has_method_source(binding_case, client):
    db, process, activity, _, _, node = binding_case
    db.add(
        NodeActivityLink(
            process_id=process.id,
            node_key=node.node_key,
            activity_id=activity.id,
            relation="CONTROLS",
        )
    )
    db.commit()
    facet = _facet(_get(client, process), "METHOD")
    assert facet["status"] == "PARTIAL"
    assert any(ref["kind"] == "CONTROL" for ref in facet["refs"])


def test_process_summary_exposes_all_four_facets(binding_case, client):
    from app.services.binding_readiness import process_bindings

    db, process, _, _, _, _ = binding_case
    summary = _get(client, process)["summary"]
    assert [(f["key"], f["status"]) for f in summary["facets"]] == [
        ("GOAL", "MISSING"),
        ("TEAM", "MISSING"),
        ("RESOURCE", "MISSING"),
        ("METHOD", "MISSING"),
    ]
    assert process_bindings(db, process.id).model_dump() == summary


def test_missing_one_of_many_node_kpis_cannot_raise_node_facet(binding_case, client):
    db, process, activity, _, _, node = binding_case
    second = ProcessArch(code=f"SEC-{process.code}", name="第二活动", level=4, parent_id=process.id)
    db.add(second)
    db.flush()
    db.add_all(
        [
            NodeActivityLink(
                process_id=process.id,
                node_key=node.node_key,
                activity_id=activity.id,
                relation="REALIZES",
            ),
            NodeActivityLink(
                process_id=process.id,
                node_key=node.node_key,
                activity_id=second.id,
                relation="PART_OF",
            ),
        ]
    )
    db.add(
        KpiDefinition(
            code=f"MAP-{process.code}",
            name="活动指标",
            dimension="EFFICIENCY",
            process_id=process.id,
            activity_id=activity.id,
            target_value=0,
            measurement={"source_kind": "EXECUTION_ELAPSED"},
        )
    )
    db.commit()
    try:
        data = _get(client, process)
        assert data["nodes"][0]["activity_ids"] == sorted([activity.id, second.id])
        goal = next(f for f in data["nodes"][0]["facets"] if f["key"] == "GOAL")
        assert goal["status"] == "PARTIAL"
        assert data["nodes"][0]["marker"] == "yellow"
    finally:
        db.query(NodeActivityLink).filter_by(activity_id=second.id).delete()
        db.delete(second)
        db.commit()


def test_stale_version_relation_does_not_hide_current_pointer(binding_case, client):
    db, process, activity, _, _, node = binding_case
    old = ProcessModelVersion(process_id=process.id, version=1, status="SUPERSEDED", snapshot={})
    current = ProcessModelVersion(
        process_id=process.id,
        version=2,
        status="DRAFT",
        snapshot={
            "nodes": [
                {
                    "node_key": node.node_key,
                    "name": node.name,
                    "node_type": "TASK",
                    "process_arch_id": activity.id,
                }
            ],
            "edges": [],
        },
    )
    db.add_all([old, current])
    db.flush()
    db.add(
        NodeActivityLink(
            process_id=process.id,
            model_version_id=old.id,
            node_key=node.node_key,
            activity_id=activity.id,
            relation="REALIZES",
        )
    )
    db.commit()
    assert _get(client, process)["nodes"][0]["activity_ids"] == [activity.id]


def test_binding_refresh_lifecycle():
    import shutil
    import subprocess
    from pathlib import Path

    if not shutil.which("node"):
        pytest.skip("Node is needed for the native ES-module lifecycle regression")
    result = subprocess.run(
        ["node", "tests/binding_lifecycle.mjs"],
        cwd=Path(__file__).parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("category,facet_key", [("SOP", "METHOD"), ("CHECKLIST", "RESOURCE")])
def test_sibling_document_node_key_collision_not_direct(binding_case, client, category, facet_key):
    db, process, _, _, _, node = binding_case
    sibling = ProcessArch(
        code=f"SIB-{process.code}", name="兄弟活动", level=4, parent_id=process.id
    )
    db.add(sibling)
    db.flush()
    document = ProcessDocument(
        process_id=sibling.id,
        code=f"SIBDOC-{process.code}",
        title="兄弟设计专用文档",
        category=category,
        node_key=node.node_key,
        control_points="兄弟控制",
    )
    document.versions = [ProcessDocumentVersion(version_label="1.0", status="EFFECTIVE")]
    db.add(document)
    db.commit()
    try:
        data = _get(client, process)
        first = next(a for a in data["activities"] if a["activity_name"] == "测试活动")
        facet = next(f for f in first["facets"] if f["key"] == facet_key)
        assert facet["status"] == "MISSING"
        assert not any(ref["label"] == "兄弟设计专用文档" for ref in facet["refs"])
    finally:
        db.delete(document)
        db.commit()
        db.delete(sibling)
        db.commit()


def test_process_default_checklist_is_partial_inherited(binding_case, client):
    db, process, _, _, _, _ = binding_case
    document = ProcessDocument(
        process_id=process.id,
        code=f"DEFAULT-{process.code}",
        title="流程通用检查表",
        category="CHECKLIST",
    )
    document.versions = [ProcessDocumentVersion(version_label="1.0", status="EFFECTIVE")]
    db.add(document)
    db.commit()
    facet = _facet(_get(client, process), "RESOURCE")
    assert facet["status"] == "PARTIAL"
    assert any(
        ref["label"] == "流程通用检查表" and ref["source"] == "INHERITED" for ref in facet["refs"]
    )


def test_current_node_evidence_conflict_and_stale_version(binding_case, client):
    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget

    db, process, activity, _, _, node = binding_case
    current = ProcessModelVersion(
        process_id=process.id,
        version=1,
        status="PUBLISHED",
        snapshot={
            "nodes": [
                {
                    "node_key": node.node_key,
                    "name": node.name,
                    "node_type": "TASK",
                    "process_arch_id": activity.id,
                }
            ],
            "edges": [],
        },
    )
    document = ProcessDocument(
        process_id=process.id,
        code=f"NODEDOC-{process.code}",
        title="节点证据标准",
        category="SOP",
        node_key=node.node_key,
    )
    docver = ProcessDocumentVersion(document=document, version_label="1.0", status="EFFECTIVE")
    db.add_all([current, document])
    db.flush()
    target = EvidenceClaimTarget(target_type="NODE", target_id=node.id, model_version_id=current.id)
    claim = EvidenceClaim(
        process_id=process.id,
        claim="当前节点控制证据",
        claim_type="CONTROL",
        source_type="DOCUMENT_VERSION",
        source_id=docver.id,
        source_hash="a" * 64,
        method="DOCUMENTED",
        status="SUPPORTED",
        targets=[target],
    )
    db.add(claim)
    db.commit()
    try:
        facet = _facet(_get(client, process), "METHOD")
        assert facet["status"] == "READY"
        claim.status = "CONFLICTED"
        db.commit()
        data = _get(client, process)
        assert _facet(data, "METHOD")["status"] == "CONFLICT"
        assert (
            next(f for f in data["nodes"][0]["facets"] if f["key"] == "METHOD")["status"]
            == "CONFLICT"
        )
        current2 = ProcessModelVersion(
            process_id=process.id, version=2, status="DRAFT", snapshot=current.snapshot
        )
        db.add(current2)
        db.commit()
        assert _facet(_get(client, process), "METHOD")["status"] == "PARTIAL"
    finally:
        db.delete(claim)
        db.commit()


def test_private_log_claim_does_not_leak_through_public_design(binding_case, viewer_client):
    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget
    from app.models.log_import import ProcessLogImport
    from app.models.org import OrgUnit

    db, process, activity, _, _, _ = binding_case
    org = OrgUnit(
        code=f"LOGORG-{process.code}", name="日志组织", type="DEPARTMENT", path="/private/"
    )
    db.add(org)
    db.flush()
    process.org_unit_id = org.id
    log = ProcessLogImport(
        process_id=process.id, file_name="private.csv", checksum="a" * 64, status="COMMITTED"
    )
    db.add(log)
    db.flush()
    claim = EvidenceClaim(
        process_id=process.id,
        claim="受限日志证据内容",
        claim_type="CONTROL",
        source_type="LOG_IMPORT",
        source_id=log.id,
        method="LOGGED",
        status="SUPPORTED",
        targets=[EvidenceClaimTarget(target_type="ACTIVITY", target_id=activity.id)],
    )
    db.add(claim)
    db.commit()
    try:
        assert "受限日志证据内容" not in str(_get(viewer_client, process))
    finally:
        db.delete(claim)
        db.flush()
        db.delete(log)
        process.org_unit_id = None
        db.commit()
        db.delete(org)
        db.commit()


def test_cross_process_mapping_is_conflict_without_foreign_details(binding_case, client):
    db, process, _, other, _, node = binding_case
    foreign = ProcessArch(
        code=f"FA-{process.code}", name="不能泄露的外部活动", level=4, parent_id=other.id
    )
    db.add(foreign)
    db.flush()
    db.add(
        NodeActivityLink(
            process_id=process.id,
            node_key=node.node_key,
            activity_id=foreign.id,
            relation="REALIZES",
        )
    )
    db.commit()
    try:
        data = _get(client, process)
        assert data["nodes"][0]["status"] == "CONFLICT"
        assert data["nodes"][0]["activity_ids"] == []
        assert data["summary"]["overall"] == "CONFLICT"
        assert "不能泄露的外部活动" not in str(data)
    finally:
        db.query(NodeActivityLink).filter_by(activity_id=foreign.id).delete()
        db.delete(foreign)
        db.commit()
