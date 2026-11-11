"""P3a：作业归属、固定版本与不知道就明示。"""

from copy import deepcopy

import pytest
from sqlalchemy import func, select
from test_publish_gate_bindings import add_a, clean_documents, complete_performance, publish
from test_publish_gate_bindings import gate_case as shared_gate_case

from app.core.database import SessionLocal
from app.models.user import AuditLog, User
from app.models.workload import WorkMeasurementStandard

API = "/api/v1"
gate_case = pytest.fixture(name="gate_case")(shared_gate_case.__wrapped__)


def collect(case, scope="POSITION", subject_id=None):
    from app.services import handbook_scope

    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == "admin"))
        return handbook_scope.collect(db, scope, subject_id or case["position"], actor)


def test_position_steps_do_not_include_other_position_node(client, gate_case):
    payload = deepcopy(gate_case["payload"])
    payload["nodes"][1]["owner_position_id"] = None
    payload["nodes"][0]["description"] = "按订单核对物料"
    assert client.put(f"{API}/processes/{gate_case['pid']}/design", json=payload).status_code == 200
    publish(client, gate_case)
    result = collect(gate_case)
    assert [s["node_key"] for s in result["steps"]] == ["n1"]
    assert result["steps"][0]["instruction"] == "按订单核对物料"
    assert result["steps"][0]["assignment_label"] == "节点责任岗位（不自动等于R）"


@pytest.mark.parametrize("raci", ["A", "C", "I"])
def test_role_aci_is_collaboration_not_execution(client, gate_case, raci):
    response = client.post(
        API + "/governance/raci",
        json={
            "process_id": gate_case["pid"],
            "activity_id": gate_case["aid"],
            "role_id": gate_case["role"],
            "matter": "协作",
            "raci": raci,
        },
    )
    assert response.status_code == 201, response.text
    publish(client, gate_case)
    result = collect(gate_case, "ROLE", gate_case["role"])
    assert result["steps"] == []
    assert [r["raci"] for r in result["collaboration"]] == [raci]


def test_actual_work_does_not_assign_steps(client, gate_case):
    # 已验证工时只能证明测量岗位，不产生作业分派。
    payload = deepcopy(gate_case["payload"])
    for node in payload["nodes"]:
        node["owner_position_id"] = None
    assert client.put(f"{API}/processes/{gate_case['pid']}/design", json=payload).status_code == 200
    publish(client, gate_case)
    assert collect(gate_case)["steps"] == []


def test_role_r_is_scoped_to_node(client, gate_case):
    response = client.post(
        API + "/governance/raci",
        json={
            "process_id": gate_case["pid"],
            "node_key": "n1",
            "role_id": gate_case["role"],
            "matter": "执行",
            "raci": "R",
        },
    )
    assert response.status_code == 201, response.text
    publish(client, gate_case)
    result = collect(gate_case, "ROLE", gate_case["role"])
    assert [s["node_key"] for s in result["steps"]] == ["n1"]
    assert result["steps"][0]["assignment_label"] == "节点RACI-R"


def test_published_steps_ignore_working_copy(client, gate_case):
    publish(client, gate_case)
    original = collect(gate_case)
    assert (
        client.put(
            f"{API}/processes/{gate_case['pid']}/design",
            json={
                "nodes": [
                    {
                        "node_key": "draft",
                        "name": "工作版",
                        "node_type": "TASK",
                        "owner_position_id": gate_case["position"],
                    }
                ],
                "edges": [],
            },
        ).status_code
        == 200
    )
    assert collect(gate_case)["steps"] == original["steps"]


def test_scope_read_only_and_invalid_subject(client, gate_case):
    from fastapi import HTTPException

    publish(client, gate_case)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditLog))
    collect(gate_case)
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog)) == before
    with pytest.raises(HTTPException) as error:
        collect(gate_case, "PERSON")
    assert error.value.status_code == 400


def preview(case, scope="POSITION", subject_id=None, username="admin"):
    from app.services import handbook

    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == username))
        return handbook.preview(
            db, scope, subject_id or case["position"], actor, application_url="http://testserver/"
        )


def test_unknown_instructions_and_exceptions_are_explicit(client, gate_case):
    publish(client, gate_case)
    data = preview(gate_case)
    assert len(data.entries) == 2
    assert all(e["instruction_label"] == "原依据未明确" for e in data.entries)
    assert all(e["exception_label"] == "原依据未明确" for e in data.entries)
    assert data.can_compile and not data.can_submit_review


def test_source_version_is_fixed(client, gate_case):
    import io

    from app.models.process_document import ProcessDocument
    from app.services.storage import get_storage

    complete_performance(gate_case)
    with SessionLocal() as db:
        doc = db.scalar(
            select(ProcessDocument).where(ProcessDocument.process_id == gate_case["aid"])
        )
        version = doc.versions[0]
        key = f"handbook-test/{gate_case['aid']}.txt"
        checksum, size = get_storage().save(key, io.BytesIO(b"Original work instruction"), 1000)
        version.storage_key = key
        version.checksum = checksum
        version.size_bytes = size
        version.file_name = "work.txt"
        doc.exception_terms = "例外时暂停，按原授权复核"
        docid, vid = doc.id, version.id
        db.commit()
    publish(client, gate_case)
    try:
        data = preview(gate_case)
        sources = data.entries[0]["documents"]
        assert sources[0]["document_id"] == docid and sources[0]["version_id"] == vid
        assert str(vid) in sources[0]["download_url"]
        assert sources[0]["openable"]
        assert data.entries[0]["exception_label"] == "有原例外条款／规则"
    finally:
        clean_documents(gate_case)


def test_no_file_is_not_openable(client, gate_case):
    complete_performance(gate_case)
    publish(client, gate_case)
    try:
        data = preview(gate_case)
        assert data.entries[0]["documents"]
        assert not data.entries[0]["documents"][0]["openable"]
        assert any(g["code"] == "INSTRUCTION_MISSING" for g in data.gaps)
    finally:
        clean_documents(gate_case)


def test_preview_deterministic_read_only(client, gate_case):
    publish(client, gate_case)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditLog))
    a, b = preview(gate_case), preview(gate_case)
    assert a.input_hash == b.input_hash
    assert a.content_hash == b.content_hash
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AuditLog)) == before


def test_hidden_source_not_exposed(client, gate_case):
    from app.models.org import OrgUnit
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion

    with SessionLocal() as db:
        org = OrgUnit(code="HBORG-" + str(gate_case["aid"]), name="受限组织", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        oid = org.id
        doc = ProcessDocument(
            process_id=gate_case["aid"],
            code="HBSECRET-" + str(oid),
            title="SECRET_HANDBOOK_SOP",
            description="SECRET_DESCRIPTION",
            exception_terms="SECRET_EXCEPTION",
            category="SOP",
            org_unit_id=oid,
        )
        db.add(doc)
        db.flush()
        db.add(ProcessDocumentVersion(document_id=doc.id, version_label="1.0", status="EFFECTIVE"))
        db.commit()
    publish(client, gate_case)
    try:
        data = preview(gate_case, username="viewer")
        assert "SECRET_" not in data.model_dump_json()
        assert not data.can_compile
        assert any(g["code"] == "SOURCE_RESTRICTED" for g in data.gaps)
    finally:
        clean_documents(gate_case)
        with SessionLocal() as db:
            db.delete(db.get(OrgUnit, oid))
            db.commit()


def test_inherited_form_not_direct(client, gate_case):
    from app.models.execution import FormDefinition

    with SessionLocal() as db:
        forms = list(
            db.scalars(select(FormDefinition).where(FormDefinition.process_id == gate_case["pid"]))
        )
        db.delete(forms[1])
        db.flush()
        forms[0].node_key = ""
        db.commit()
    publish(client, gate_case)
    data = preview(gate_case)
    assert data.entries[0]["forms"][0]["source"] == "INHERITED"
    assert not data.can_submit_review


def api_preview(client, case, scope="POSITION", subject_id=None):
    response = client.post(
        API + "/handbooks/preview",
        json={"scope": scope, "subject_id": subject_id or case["position"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def generate(client, case, scope="POSITION", subject_id=None):
    data = api_preview(client, case, scope, subject_id)
    response = client.post(
        API + "/handbooks",
        json={
            "scope": scope,
            "subject_id": subject_id or case["position"],
            "expected_input_hash": data["input_hash"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_ready(client, case):
    import io

    from app.models.process_document import ProcessDocument
    from app.services.storage import get_storage

    add_a(client, case)
    complete_performance(case)
    with SessionLocal() as db:
        doc = db.scalar(select(ProcessDocument).where(ProcessDocument.process_id == case["aid"]))
        doc.exception_terms = "例外时停止作业，按原条款复核"
        ver = doc.versions[0]
        key = f"hb-ready/{case['aid']}.txt"
        checksum, size = get_storage().save(
            key, io.BytesIO(b"Synthetic original instructions"), 1000
        )
        ver.storage_key, ver.checksum, ver.size_bytes, ver.file_name = (
            key,
            checksum,
            size,
            "instructions.txt",
        )
        db.commit()
    publish(client, case)


def transition(client, packet, status):
    return client.post(
        f"{API}/process-documents/{packet['document_id']}/versions/{packet['version_id']}/transition",
        json={"status": status},
    )


def test_handbook_full_lifecycle(client, gate_case):
    make_ready(client, gate_case)
    try:
        data = api_preview(client, gate_case)
        assert data["can_submit_review"]
        packet = generate(client, gate_case)
        for status in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            moved = transition(client, packet, status)
            assert moved.status_code == 200, moved.text
        fixed = client.get(f"{API}/handbooks/{packet['version_id']}")
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["status"] == "EFFECTIVE"
        assert fixed.json()["manifest"]["kind"] == "HANDBOOK"
        assert client.get(fixed.json()["download_url"]).status_code == 200
    finally:
        clean_documents(gate_case)


def test_incomplete_draft_cannot_review(client, gate_case):
    publish(client, gate_case)
    try:
        packet = generate(client, gate_case)
        assert packet["status"] == "DRAFT"
        assert transition(client, packet, "IN_REVIEW").status_code == 409
        assert transition(client, packet, "RETIRED").status_code == 200
    finally:
        clean_documents(gate_case)


@pytest.mark.parametrize("status", ["IN_REVIEW", "APPROVED", "EFFECTIVE"])
def test_source_change_blocks_each_transition(client, gate_case, status):
    make_ready(client, gate_case)
    try:
        packet = generate(client, gate_case)
        for stage in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            if stage == status:
                break
            assert transition(client, packet, stage).status_code == 200
        with SessionLocal() as db:
            db.get(WorkMeasurementStandard, gate_case["standard"]).standard_minutes = 9
            db.commit()
        assert transition(client, packet, status).status_code == 409
    finally:
        clean_documents(gate_case)


def test_stale_preview_hash_and_identical_version_reuse(client, gate_case):
    publish(client, gate_case)
    try:
        stale = client.post(
            API + "/handbooks",
            json={
                "scope": "POSITION",
                "subject_id": gate_case["position"],
                "expected_input_hash": "0" * 64,
            },
        )
        assert stale.status_code == 409
        a, b = generate(client, gate_case), generate(client, gate_case)
        assert a["version_id"] == b["version_id"]
    finally:
        clean_documents(gate_case)


def test_upload_and_asset_route_cannot_bypass(client, viewer_client, gate_case):
    publish(client, gate_case)
    try:
        packet = generate(client, gate_case)
        uploaded = client.post(
            f"{API}/process-documents/{packet['document_id']}/versions/upload",
            data={"version_label": "2.0"},
            files={"file": ("fake.txt", b"fake", "text/plain")},
        )
        assert uploaded.status_code == 400
        assert client.get(f"{API}/asset-packages/{packet['version_id']}").status_code == 404
        assert (
            client.post(
                API + "/handbooks",
                json={
                    "scope": "POSITION",
                    "subject_id": gate_case["position"],
                    "expected_input_hash": api_preview(client, gate_case)["input_hash"],
                },
                headers=viewer_client.headers,
            ).status_code
            == 403
        )
    finally:
        clean_documents(gate_case)


def test_hidden_historical_source_blocks_all_read_paths(client, viewer_client, gate_case):
    from app.models.org import OrgUnit
    from app.models.process_document import ProcessDocument

    make_ready(client, gate_case)
    try:
        packet = generate(client, gate_case)
        with SessionLocal() as db:
            org = OrgUnit(
                code="HBHIST-" + str(gate_case["aid"]), name="限制历史", type="DEPARTMENT"
            )
            db.add(org)
            db.flush()
            org.path = f"/{org.id}/"
            oid = org.id
            db.scalar(
                select(ProcessDocument).where(ProcessDocument.process_id == gate_case["aid"])
            ).org_unit_id = oid
            db.commit()
        for path in [
            f"/handbooks/{packet['version_id']}",
            f"/handbooks?scope=POSITION&subject_id={gate_case['position']}",
            f"/process-documents/{packet['document_id']}",
            packet["download_url"].replace(API, ""),
            f"/process-documents/{packet['document_id']}/versions/{packet['version_id']}/preview",
        ]:
            response = viewer_client.get(API + path)
            assert response.status_code == 404, (path, response.text)
    finally:
        clean_documents(gate_case)
        with SessionLocal() as db:
            db.delete(db.get(OrgUnit, oid))
            db.commit()


def test_fixed_source_url_is_reachable(client, gate_case):
    make_ready(client, gate_case)
    try:
        data = api_preview(client, gate_case)
        source = data["entries"][0]["documents"][0]
        response = client.get(source["download_url"].replace("http://testserver", ""))
        assert response.status_code == 200, response.text
        response.close()
    finally:
        clean_documents(gate_case)


def test_fixed_historical_source_remains_readable_after_upgrade(client, gate_case):
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion

    make_ready(client, gate_case)
    try:
        data = api_preview(client, gate_case)
        source = data["entries"][0]["documents"][0]
        with SessionLocal() as db:
            doc = db.get(ProcessDocument, source["document_id"])
            old = db.get(ProcessDocumentVersion, source["version_id"])
            old.status = "SUPERSEDED"
            new = ProcessDocumentVersion(
                document_id=doc.id, version_label="2.0", status="EFFECTIVE"
            )
            db.add(new)
            db.commit()
        response = client.get(source["download_url"].replace("http://testserver", ""))
        assert response.status_code == 200, response.text
        response.close()
    finally:
        clean_documents(gate_case)


def test_process_source_visibility_is_enforced(client, viewer_client, gate_case):
    from app.models.org import OrgUnit
    from app.models.process_document import ProcessDocument

    make_ready(client, gate_case)
    with SessionLocal() as db:
        org = OrgUnit(
            code="HBPROC-" + str(gate_case["aid"]), name="受限流程组织", type="DEPARTMENT"
        )
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        doc = db.scalar(
            select(ProcessDocument).where(ProcessDocument.process_id == gate_case["aid"])
        )
        doc.org_unit_id = org.id
        db.commit()
        did = doc.id
        vid = doc.versions[0].id
    try:
        response = viewer_client.get(f"{API}/handbooks/source?document_id={did}&version_id={vid}")
        assert response.status_code == 404, response.text
    finally:
        clean_documents(gate_case)
        with SessionLocal() as db:
            db.delete(db.get(OrgUnit, org.id))
            db.commit()


def test_process_rule_is_not_exception_evidence(client, gate_case):
    from app.models.execution import ProcessRule

    complete_performance(gate_case)
    with SessionLocal() as db:
        db.add(
            ProcessRule(
                process_id=gate_case["pid"],
                node_key="n1",
                name="普通分支",
                conditions=[],
                target_node_key="n2",
            )
        )
        db.commit()
    publish(client, gate_case)
    try:
        data = api_preview(client, gate_case)
        assert data["entries"][0]["exception_label"] == "原依据未明确"
        assert any(g["code"] == "EXCEPTION_UNDEFINED" for g in data["gaps"])
    finally:
        clean_documents(gate_case)


def test_handbook_status_labels_are_backend_labels(client, gate_case):
    publish(client, gate_case)
    try:
        packet = generate(client, gate_case)
        assert packet["status"] == "DRAFT"
        assert packet["status_label"] == "草稿"
    finally:
        clean_documents(gate_case)


def test_role_handbook_preview_is_supported(client, gate_case):
    publish(client, gate_case)
    role = client.get(API + "/governance/roles?active_only=true").json()[0]
    response = client.post(
        API + "/handbooks/preview", json={"scope": "ROLE", "subject_id": role["id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["subject"]["scope"] == "ROLE"
