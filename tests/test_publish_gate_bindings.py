"""P2′ 使用入口不能把设计发布或历史绿灯当成完整绑定。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.core.database import SessionLocal
from app.models.execution import FormDefinition, ProcessExecutionConfig
from app.models.org import Position
from app.models.process import ProcessArch, ProcessModelVersion
from app.models.raci import GovernanceRole, GovernanceRoleMember, RaciAssignment
from app.models.user import AuditLog, User
from app.models.workload import WorkMeasurementStandard
from app.services import binding_readiness

API = "/api/v1"


@pytest.fixture
def gate_case(client):
    suffix = uuid4().hex[:8]
    p = client.post(
        API + "/process-map",
        json={"code": "GATE-" + suffix, "name": "门禁流程", "level": 3, "publish_policy": "direct"},
    ).json()
    a = client.post(
        API + "/process-map",
        json={"code": "GA-" + suffix, "name": "门禁活动", "level": 4, "parent_id": p["id"]},
    ).json()
    with SessionLocal() as db:
        position = Position(code="GP-" + suffix, name="门禁岗位")
        role = GovernanceRole(code="GR-" + suffix, name="门禁负责角色", is_active=True)
        db.add_all([position, role])
        db.flush()
        standard = WorkMeasurementStandard(
            code="GS-" + suffix,
            name="验证工时",
            activity_id=a["id"],
            position_id=position.id,
            standard_minutes=5,
            monthly_frequency=10,
            status="VERIFIED",
        )
        db.add(standard)
        db.commit()
        member = User(
            username="gate-member-" + suffix,
            display_name="岗位成员",
            password_hash="not-a-login",
            position_id=position.id,
        )
        db.add(member)
        db.flush()
        db.add(GovernanceRoleMember(role_id=role.id, user_id=member.id))
        db.commit()
        ids = {
            "position": position.id,
            "role": role.id,
            "standard": standard.id,
            "member": member.id,
        }
    payload = {
        "nodes": [
            {
                "node_key": key,
                "name": key,
                "node_type": "TASK",
                "process_arch_id": a["id"],
                "owner_position_id": ids["position"],
            }
            for key in ["n1", "n2"]
        ],
        "edges": [{"source_key": "n1", "target_key": "n2"}],
    }
    response = client.put(f"{API}/processes/{p['id']}/design", json=payload)
    assert response.status_code == 200, response.text
    for key in ["n1", "n2"]:
        response = client.post(
            API + "/execution/forms",
            json={"process_id": p["id"], "node_key": key, "name": key + "记录", "fields": []},
        )
        assert response.status_code == 201, response.text
    case = {"pid": p["id"], "aid": a["id"], "payload": payload, **ids}
    yield case
    with SessionLocal() as db:
        db.execute(
            delete(ProcessExecutionConfig).where(ProcessExecutionConfig.process_id == p["id"])
        )
        db.execute(delete(RaciAssignment).where(RaciAssignment.process_id == p["id"]))
        db.execute(delete(FormDefinition).where(FormDefinition.process_id == p["id"]))
        db.execute(
            delete(WorkMeasurementStandard).where(WorkMeasurementStandard.id == ids["standard"])
        )
        db.commit()
    response = client.delete(f"{API}/process-map/{p['id']}")
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        db.execute(delete(GovernanceRoleMember).where(GovernanceRoleMember.role_id == ids["role"]))
        db.delete(db.get(User, ids["member"]))
        db.delete(db.get(GovernanceRole, ids["role"]))
        db.delete(db.get(Position, ids["position"]))
        db.commit()


def add_a(client, case, node_key=None):
    response = client.post(
        API + "/governance/raci",
        json={
            "process_id": case["pid"],
            "matter": "负责",
            "role_id": case["role"],
            "raci": "A",
            **({"node_key": node_key} if node_key else {"activity_id": case["aid"]}),
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def publish(client, case):
    response = client.post(
        f"{API}/processes/{case['pid']}/design/publish",
        json={"change_note": "门禁合成发布", "self_publish_reason": "隔离测试同一账号核对绑定门禁"},
    )
    assert response.status_code == 200, response.text
    case["vid"] = response.json()["version_id"]
    return response.json()


def gate(case, profile="EXECUTION", **extra):
    assert callable(getattr(binding_readiness, "binding_gate", None)), "缺少使用入口档位投影"
    with SessionLocal() as db:
        return binding_readiness.binding_gate(
            db, case["pid"], profile=profile, model_version_id=case["vid"], **extra
        )


def test_missing_a_allows_publish_but_blocks_execution_and_performance(client, gate_case):
    preview = client.get(f"{API}/processes/{gate_case['pid']}/design/publish-preview").json()
    assert preview["can_publish"] is True
    assert any("绑定" in x for x in preview["warnings"])
    published = publish(client, gate_case)
    assert published["binding_warnings"]
    with SessionLocal() as db:
        assert db.get(ProcessModelVersion, gate_case["vid"]).binding_snapshot is not None
    for profile in ["EXECUTION", "PERFORMANCE"]:
        result = gate(gate_case, profile)
        assert not result.ready
        failure = next(b for b in result.blockers if b.code == "BINDING_TEAM_INCOMPLETE")
        assert any("n1" in t for t in failure.targets)


def test_profile_projection_uses_one_readiness_result(client, gate_case):
    add_a(client, gate_case)
    publish(client, gate_case)
    assert gate(gate_case).ready is True
    performance = gate(gate_case, "PERFORMANCE")
    assert not performance.ready
    assert {b.code for b in performance.blockers} == {
        "BINDING_GOAL_INCOMPLETE",
        "BINDING_METHOD_INCOMPLETE",
    }


def test_node_scope_does_not_cover_sibling(client, gate_case):
    add_a(client, gate_case, "n1")
    publish(client, gate_case)
    result = gate(gate_case)
    assert not result.ready
    assert any("n2" in t for b in result.blockers for t in b.targets)


def test_default_form_does_not_satisfy_carrier(client, gate_case):
    add_a(client, gate_case)
    with SessionLocal() as db:
        forms = list(
            db.scalars(select(FormDefinition).where(FormDefinition.process_id == gate_case["pid"]))
        )
        db.delete(forms[1])
        db.flush()
        forms[0].node_key = ""
        db.commit()
    publish(client, gate_case)
    assert "BINDING_RESOURCE_INCOMPLETE" in {b.code for b in gate(gate_case).blockers}


def test_gate_uses_requested_published_not_latest_draft(client, gate_case):
    add_a(client, gate_case)
    publish(client, gate_case)
    response = client.put(
        f"{API}/processes/{gate_case['pid']}/design",
        json={
            "nodes": [{"node_key": "broken", "name": "工作版缺项", "node_type": "TASK"}],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    result = gate(gate_case)
    assert result.model_version_id == gate_case["vid"]
    assert result.ready is True


def test_gate_is_read_only(client, gate_case):
    add_a(client, gate_case)
    publish(client, gate_case)
    classes = [AuditLog, ProcessArch, ProcessModelVersion, RaciAssignment]
    with SessionLocal() as db:
        before = [db.scalar(select(func.count()).select_from(cls)) for cls in classes]
    first, second = gate(gate_case), gate(gate_case)
    assert first.fingerprint == second.fingerprint
    with SessionLocal() as db:
        assert before == [db.scalar(select(func.count()).select_from(cls)) for cls in classes]


def prepare(client, case):
    from test_execution_readiness import ready_payload

    path = f"{API}/execution/readiness?process_id={case['pid']}"
    data = client.get(path).json()
    response = client.put(path, json=ready_payload(client, data["revision"]))
    assert response.status_code == 200, response.text
    return response.json()


def decide(owner_client, case, revision, decision="ACCEPT"):
    return owner_client.post(
        f"{API}/execution/readiness/confirm?process_id={case['pid']}",
        json={"expected_revision": revision, "decision": decision, "evidence": "本人核对原绑定"},
    )


def test_not_applicable_cannot_waive_execution_bindings(client, owner_client, gate_case):
    publish(client, gate_case)
    data = prepare(client, gate_case)
    assert decide(owner_client, gate_case, data["revision"]).status_code == 400
    assert decide(owner_client, gate_case, data["revision"], "RETURN").status_code == 200


@pytest.mark.parametrize("source", ["a", "standard", "carrier"])
def test_binding_change_invalidates_confirmation(client, owner_client, gate_case, source):
    add_a(client, gate_case)
    publish(client, gate_case)
    data = prepare(client, gate_case)
    confirmed = decide(owner_client, gate_case, data["revision"])
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["confirmed"] is True
    with SessionLocal() as db:
        if source == "a":
            db.scalar(
                select(RaciAssignment).where(RaciAssignment.process_id == gate_case["pid"])
            ).raci = "R"
        elif source == "standard":
            db.get(WorkMeasurementStandard, gate_case["standard"]).standard_minutes = 6
        else:
            db.scalar(
                select(FormDefinition).where(FormDefinition.process_id == gate_case["pid"])
            ).name = "载体内容修订"
        db.commit()
    changed = client.get(f"{API}/execution/readiness?process_id={gate_case['pid']}").json()
    assert changed["confirmed"] is False
    assert changed["fingerprint"] != confirmed.json()["fingerprint"]
    assert decide(owner_client, gate_case, changed["revision"]).status_code == 400


def complete_performance(case):
    from app.models.monitor import KpiDefinition
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion

    with SessionLocal() as db:
        db.add(
            KpiDefinition(
                code="GK-" + uuid4().hex[:8],
                name="活动指标",
                dimension="EFFICIENCY",
                process_id=case["pid"],
                activity_id=case["aid"],
                target_value=10,
                measurement={"formula": "分钟/次"},
                direction="LOWER_BETTER",
            )
        )
        doc = ProcessDocument(
            process_id=case["aid"],
            code="GD-" + uuid4().hex[:8],
            title="活动标准",
            category="SOP",
            control_points="执行后核对记录",
        )
        db.add(doc)
        db.flush()
        db.add(ProcessDocumentVersion(document_id=doc.id, version_label="1.0", status="EFFECTIVE"))
        db.commit()


def clean_documents(case):
    from app.models.monitor import KpiDefinition
    from app.models.process_document import (
        CompiledAssetComponent,
        ProcessDocument,
    )

    with SessionLocal() as db:
        docs = list(
            db.scalars(
                select(ProcessDocument).where(
                    (ProcessDocument.process_id.in_([case["pid"], case["aid"]]))
                    | (ProcessDocument.position_id == case["position"])
                )
            )
        )
        for doc in docs:
            for version in doc.versions:
                db.execute(
                    delete(CompiledAssetComponent).where(
                        CompiledAssetComponent.document_version_id == version.id
                    )
                )
                if version.storage_key:
                    from app.services.storage import get_storage

                    get_storage().delete(version.storage_key)
            db.delete(doc)
        db.execute(delete(KpiDefinition).where(KpiDefinition.activity_id == case["aid"]))
        db.commit()


def create_package(client, case):
    response = client.post(f"{API}/processes/{case['pid']}/asset-packages")
    assert response.status_code == 200, response.text
    return response.json()


def move_package(client, package, target, generic=False):
    path = (
        f"/process-documents/{package['document_id']}/versions/{package['version_id']}/transition"
        if generic
        else f"/asset-packages/{package['version_id']}/transition"
    )
    return client.post(API + path, json={"status": target})


def test_asset_draft_allowed_review_blocked_missing_a(client, gate_case):
    publish(client, gate_case)
    try:
        package = create_package(client, gate_case)
        assert package["status"] == "DRAFT"
        for generic in [False, True]:
            assert move_package(client, package, "IN_REVIEW", generic).status_code == 409
    finally:
        clean_documents(gate_case)


@pytest.mark.parametrize("target", ["APPROVED", "EFFECTIVE"])
def test_asset_approval_rechecks_sources(client, gate_case, target):
    add_a(client, gate_case)
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        package = create_package(client, gate_case)
        assert move_package(client, package, "IN_REVIEW").status_code == 200
        if target == "EFFECTIVE":
            assert move_package(client, package, "APPROVED").status_code == 200
        with SessionLocal() as db:
            db.get(WorkMeasurementStandard, gate_case["standard"]).standard_minutes = 7
            db.commit()
        for generic in [False, True]:
            assert move_package(client, package, target, generic).status_code == 409
    finally:
        clean_documents(gate_case)


def test_asset_return_and_retire_remain_available(client, gate_case):
    add_a(client, gate_case)
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        package = create_package(client, gate_case)
        assert move_package(client, package, "IN_REVIEW").status_code == 200
        with SessionLocal() as db:
            db.get(WorkMeasurementStandard, gate_case["standard"]).status = "DRAFT"
            db.commit()
        assert move_package(client, package, "DRAFT").status_code == 200
        assert move_package(client, package, "RETIRED").status_code == 200
    finally:
        clean_documents(gate_case)


def test_generated_package_is_not_its_own_binding_source(client, gate_case):
    add_a(client, gate_case)
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        assert gate(gate_case, "PERFORMANCE").ready
        create_package(client, gate_case)
        assert gate(gate_case, "PERFORMANCE").ready
    finally:
        clean_documents(gate_case)


def job_preview(client, case):
    response = client.post(
        f"{API}/positions/{case['position']}/job-description/preview", json={"period": "2026-10-01"}
    )
    assert response.status_code == 200, response.text
    return response.json()


def compile_job(client, case):
    data = job_preview(client, case)
    response = client.post(
        f"{API}/positions/{case['position']}/job-descriptions",
        json={"period": "2026-10-01", "expected_input_hash": data["input_hash"]},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_job_draft_allowed_but_review_blocked_missing_bindings(client, gate_case):
    publish(client, gate_case)
    try:
        data = job_preview(client, gate_case)
        assert data["can_compile"] is True
        assert data.get("can_submit_review") is False
        package = compile_job(client, gate_case)
        assert move_package(client, package, "IN_REVIEW", True).status_code == 409
    finally:
        clean_documents(gate_case)


def test_job_gate_ignores_unrelated_activity(client, gate_case):
    add_a(client, gate_case)
    complete_performance(gate_case)
    client.post(
        API + "/process-map",
        json={
            "code": "UNREL-" + uuid4().hex[:8],
            "name": "其他岗位活动",
            "level": 4,
            "parent_id": gate_case["pid"],
        },
    )
    publish(client, gate_case)
    try:
        diagnostic = job_preview(client, gate_case)
        assert diagnostic.get("can_submit_review") is True, {
            "gaps": diagnostic["gaps"],
            "gates": diagnostic.get("binding_gates"),
        }
        package = compile_job(client, gate_case)
        assert move_package(client, package, "IN_REVIEW", True).status_code == 200
    finally:
        clean_documents(gate_case)


@pytest.mark.parametrize("target", ["IN_REVIEW", "APPROVED", "EFFECTIVE"])
def test_job_transition_rechecks_each_stage(client, gate_case, target):
    add_a(client, gate_case)
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        package = compile_job(client, gate_case)
        for stage in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            if stage == target:
                break
            response = move_package(client, package, stage, True)
            assert response.status_code == 200, response.text
        with SessionLocal() as db:
            db.get(WorkMeasurementStandard, gate_case["standard"]).status = "DRAFT"
            db.commit()
        assert move_package(client, package, target, True).status_code == 409
    finally:
        clean_documents(gate_case)


def test_job_input_hash_independent_of_database_row_order(client, gate_case):
    from datetime import date

    from sqlalchemy import text

    from app.models.user import User
    from app.services import job_description

    add_a(client, gate_case)
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        with SessionLocal() as db:
            if db.bind.dialect.name != "sqlite":
                pytest.skip("SQLite query-order perturbation")
            actor = db.scalar(select(User).where(User.username == "admin"))
            first = job_description.preview(db, gate_case["position"], actor, date(2026, 10, 1))
            db.execute(text("PRAGMA reverse_unordered_selects=ON"))
            second = job_description.preview(db, gate_case["position"], actor, date(2026, 10, 1))
            db.execute(text("PRAGMA reverse_unordered_selects=OFF"))
            assert first.input_hash == second.input_hash, "同一来源仅查询顺序变化不能让预览过期"
    finally:
        clean_documents(gate_case)


def link_form(client, case, form_id):
    response = client.post(
        f"{API}/processes/{case['pid']}/resource-links",
        json={"activity_id": case["aid"], "resource_type": "FORM", "ref_id": form_id},
    )
    assert response.status_code == 201, response.text


def test_linked_published_resource_ignores_unpublished_node_removal(client, gate_case):
    add_a(client, gate_case)
    with SessionLocal() as db:
        form = db.scalar(
            select(FormDefinition).where(FormDefinition.process_id == gate_case["pid"])
        )
        form_id = form.id
    link_form(client, gate_case, form_id)
    publish(client, gate_case)
    assert gate(gate_case).ready
    response = client.put(
        f"{API}/processes/{gate_case['pid']}/design",
        json={
            "nodes": [{"node_key": "draft", "name": "未发布工作版", "node_type": "TASK"}],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    assert gate(gate_case).ready, "原资源校验必须贯穿原发布版本"


@pytest.mark.parametrize("change", ["remove", "inactive", "position"])
def test_a_role_member_change_invalidates_execution_confirmation(
    client, owner_client, gate_case, change
):
    add_a(client, gate_case)
    publish(client, gate_case)
    saved = prepare(client, gate_case)
    confirmed = decide(owner_client, gate_case, saved["revision"])
    assert confirmed.status_code == 200 and confirmed.json()["confirmed"], confirmed.text
    with SessionLocal() as db:
        if change == "remove":
            db.execute(
                delete(GovernanceRoleMember).where(
                    GovernanceRoleMember.role_id == gate_case["role"]
                )
            )
        elif change == "inactive":
            db.get(User, gate_case["member"]).is_active = False
        else:
            db.get(User, gate_case["member"]).position_id = None
        db.commit()
    changed = client.get(f"{API}/execution/readiness?process_id={gate_case['pid']}").json()
    assert not changed["confirmed"]
    assert changed["fingerprint"] != confirmed.json()["fingerprint"]
    assert not changed["binding_gate"]["ready"]


def test_asset_container_cannot_upload_a_bypass_version(client, gate_case):
    publish(client, gate_case)
    try:
        package = create_package(client, gate_case)
        response = client.post(
            f"{API}/process-documents/{package['document_id']}/versions/upload",
            data={"version_label": "2.0"},
            files={"file": ("replacement.txt", b"synthetic compiled replacement", "text/plain")},
        )
        assert response.status_code == 400, "资产包容器只能重新编译，不能人工替换"
    finally:
        clean_documents(gate_case)


def test_default_form_link_cannot_become_direct_record_carrier(client, gate_case):
    add_a(client, gate_case)
    with SessionLocal() as db:
        forms = list(
            db.scalars(select(FormDefinition).where(FormDefinition.process_id == gate_case["pid"]))
        )
        db.delete(forms[1])
        db.flush()
        forms[0].node_key = ""
        form_id = forms[0].id
        db.commit()
    link_form(client, gate_case, form_id)
    publish(client, gate_case)
    assert not gate(gate_case).ready
    assert "BINDING_RESOURCE_INCOMPLETE" in {b.code for b in gate(gate_case).blockers}


def test_job_unrelated_source_change_does_not_invalidate_document(client, gate_case):
    from app.models.monitor import KpiDefinition

    add_a(client, gate_case)
    complete_performance(gate_case)
    other = client.post(
        API + "/process-map",
        json={
            "code": "UNRS-" + uuid4().hex[:8],
            "name": "无关活动",
            "level": 4,
            "parent_id": gate_case["pid"],
        },
    ).json()
    publish(client, gate_case)
    try:
        before = job_preview(client, gate_case)
        assert before["can_submit_review"]
        package = compile_job(client, gate_case)
        with SessionLocal() as db:
            db.add(
                KpiDefinition(
                    code="UNRK-" + uuid4().hex[:8],
                    name="无关指标",
                    dimension="QUALITY",
                    activity_id=other["id"],
                    process_id=gate_case["pid"],
                    target_value=2,
                )
            )
            db.commit()
        after = job_preview(client, gate_case)
        assert after["can_compile"] and after["can_submit_review"]
        assert after["input_hash"] == before["input_hash"]
        response = move_package(client, package, "IN_REVIEW", True)
        assert response.status_code == 200, response.text
    finally:
        with SessionLocal() as db:
            db.execute(delete(KpiDefinition).where(KpiDefinition.activity_id == other["id"]))
            db.commit()
        clean_documents(gate_case)


def test_job_unrelated_node_role_ambiguity_does_not_block(client, gate_case):
    add_a(client, gate_case)
    complete_performance(gate_case)
    other = client.post(
        API + "/process-map",
        json={
            "code": "UNRN-" + uuid4().hex[:8],
            "name": "其他岗位活动",
            "level": 4,
            "parent_id": gate_case["pid"],
        },
    ).json()
    payload = gate_case["payload"]
    payload["nodes"].append(
        {
            "node_key": "other",
            "name": "无关节点",
            "node_type": "TASK",
            "process_arch_id": other["id"],
        }
    )
    assert client.put(f"{API}/processes/{gate_case['pid']}/design", json=payload).status_code == 200
    role = client.get(API + "/governance/roles?active_only=true").json()[0]
    response = client.post(
        API + "/governance/raci",
        json={
            "process_id": gate_case["pid"],
            "node_key": "other",
            "role_id": role["id"],
            "matter": "其他节点负责",
            "raci": "A",
        },
    )
    assert response.status_code == 201, response.text
    publish(client, gate_case)
    try:
        assert job_preview(client, gate_case)["can_submit_review"]
    finally:
        clean_documents(gate_case)


def test_job_unrelated_restricted_source_is_not_a_compilation_dependency(
    client, viewer_client, gate_case
):
    from app.models.monitor import KpiDefinition
    from app.models.org import OrgUnit
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion

    add_a(client, gate_case)
    complete_performance(gate_case)
    other = client.post(
        API + "/process-map",
        json={
            "code": "UNRA-" + uuid4().hex[:8],
            "name": "无关保密活动",
            "level": 4,
            "parent_id": gate_case["pid"],
        },
    ).json()
    with SessionLocal() as db:
        org = OrgUnit(code="UNRORG-" + uuid4().hex[:8], name="无关受限组织", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        oid = org.id
        doc = ProcessDocument(
            process_id=other["id"],
            code="UNRD-" + uuid4().hex[:8],
            title="SECRET_UNRELATED_STANDARD",
            category="SOP",
            control_points="隐藏控制点",
            org_unit_id=oid,
        )
        db.add(doc)
        db.flush()
        did = doc.id
        db.add(ProcessDocumentVersion(document_id=did, version_label="1.0", status="EFFECTIVE"))
        db.commit()
    publish(client, gate_case)
    try:
        data = job_preview(viewer_client, gate_case)
        assert data["can_compile"] and data["can_submit_review"], data["gaps"]
        assert "SECRET_UNRELATED_STANDARD" not in data["preview_html"]
        assert not any(g["code"] == "SOURCE_RESTRICTED" for g in data["gaps"])
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ProcessDocumentVersion).where(ProcessDocumentVersion.document_id == did)
            )
            db.execute(delete(ProcessDocument).where(ProcessDocument.id == did))
            db.execute(delete(KpiDefinition).where(KpiDefinition.activity_id == other["id"]))
            db.delete(db.get(OrgUnit, oid))
            db.commit()
        clean_documents(gate_case)


def test_scoped_gate_preserves_cross_process_mapping_conflict(client, gate_case):
    from app.models.asset_graph import NodeActivityLink

    add_a(client, gate_case)
    other_process = client.post(
        API + "/process-map",
        json={"code": "INVALIDP-" + uuid4().hex[:8], "name": "其他流程", "level": 3},
    ).json()
    foreign = client.post(
        API + "/process-map",
        json={
            "code": "INVALIDA-" + uuid4().hex[:8],
            "name": "跨流程错误活动",
            "level": 4,
            "parent_id": other_process["id"],
        },
    ).json()
    try:
        with SessionLocal() as db:
            for aid in [gate_case["aid"], foreign["id"]]:
                db.add(
                    NodeActivityLink(
                        process_id=gate_case["pid"],
                        node_key="n1",
                        activity_id=aid,
                        relation="REALIZES",
                    )
                )
            db.commit()
        publish(client, gate_case)
        result = gate(gate_case, activity_ids={gate_case["aid"]})
        assert not result.ready
        assert "NODE_ACTIVITY_UNMAPPED" in {b.code for b in result.blockers}
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(NodeActivityLink).where(NodeActivityLink.process_id == gate_case["pid"])
            )
            db.commit()
        client.delete(f"{API}/process-map/{other_process['id']}")
