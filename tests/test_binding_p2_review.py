"""整片复核发现的真实边界回归，修复前必须失败。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete
from test_job_description import _compile, _fixed_model, _remove_generated, preview
from test_position_coverage import _coverage, _raci
from test_position_coverage import coverage_case as shared_coverage_case

from app.core.database import SessionLocal
from app.models.org import OrgUnit
from app.models.process_task import ProcessTaskDefinition
from app.models.workload import WorkMeasurementStandard

coverage_case = pytest.fixture(name="coverage_case")(shared_coverage_case.__wrapped__)
API = "/api/v1"


def test_fixed_history_never_discloses_restricted_source(client, viewer_client, coverage_case):
    p, a, ids = coverage_case
    with SessionLocal() as db:
        org = OrgUnit(code="ACL-" + uuid4().hex[:8], name="受限部门", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        oid = org.id
        standard = WorkMeasurementStandard(
            code="ACLWS-" + uuid4().hex[:8],
            name="CONFIDENTIAL_STANDARD_57",
            activity_id=a["id"],
            position_id=ids["position"],
            org_unit_id=oid,
            standard_minutes=57,
            monthly_frequency=10,
            status="VERIFIED",
        )
        db.add(standard)
        db.commit()
    _fixed_model(coverage_case)
    try:
        data = preview(client, coverage_case)
        created = _compile(client, coverage_case, data["input_hash"])
        assert created.status_code == 201, created.text
        saved = created.json()
        for path in [
            f"/positions/{ids['position']}/job-descriptions/{saved['version_id']}",
            f"/positions/{ids['position']}/job-descriptions",
            f"/process-documents/{saved['document_id']}",
            f"/process-documents/{saved['document_id']}/versions",
            f"/process-documents/{saved['document_id']}/versions/{saved['version_id']}/download",
            f"/process-documents/{saved['document_id']}/versions/{saved['version_id']}/preview",
        ]:
            response = viewer_client.get(API + path)
            assert response.status_code == 404, (path, response.text)
            assert "CONFIDENTIAL_STANDARD_57" not in response.text
    finally:
        _remove_generated(coverage_case)
        with SessionLocal() as db:
            db.execute(
                delete(WorkMeasurementStandard).where(WorkMeasurementStandard.org_unit_id == oid)
            )
            db.delete(db.get(OrgUnit, oid))
            db.commit()


def test_fixed_history_checks_linked_document_scope(client, viewer_client, coverage_case):
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.models.resource_link import ActivityResourceLink

    p, a, ids = coverage_case
    with SessionLocal() as db:
        org = OrgUnit(code="LINKACL-" + uuid4().hex[:8], name="受限标准部门", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        oid = org.id
        doc = ProcessDocument(
            process_id=p["id"],
            code="LINKDOC-" + uuid4().hex[:8],
            title="SECRET_LINKED_POLICY",
            category="POLICY",
            org_unit_id=oid,
        )
        db.add(doc)
        db.flush()
        did = doc.id
        db.add(ProcessDocumentVersion(document_id=did, version_label="1.0", status="EFFECTIVE"))
        db.add(
            ActivityResourceLink(
                activity_id=a["id"], resource_type="DOCUMENT", ref_id=did, ref_key=f"DOC:{did}"
            )
        )
        db.commit()
    _fixed_model(coverage_case)
    try:
        created = _compile(client, coverage_case, preview(client, coverage_case)["input_hash"])
        assert created.status_code == 201, created.text
        response = viewer_client.get(
            f"{API}/positions/{ids['position']}/job-descriptions/{created.json()['version_id']}"
        )
        assert response.status_code == 404, response.text
    finally:
        _remove_generated(coverage_case)
        with SessionLocal() as db:
            db.execute(
                delete(ActivityResourceLink).where(ActivityResourceLink.activity_id == a["id"])
            )
            db.execute(
                delete(ProcessDocumentVersion).where(ProcessDocumentVersion.document_id == did)
            )
            db.execute(delete(ProcessDocument).where(ProcessDocument.id == did))
            db.delete(db.get(OrgUnit, oid))
            db.commit()


def test_unpublished_removal_does_not_erase_published_responsibility(client, coverage_case):
    _fixed_model(coverage_case)
    p, a, ids = coverage_case
    response = client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": "n1",
                    "name": "撤掉岗位的工作版",
                    "node_type": "TASK",
                    "process_arch_id": a["id"],
                    "owner_position_id": ids["other"],
                }
            ],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    data = preview(client, coverage_case)
    assert p["id"] in [r["process_id"] for r in data["manifest"]["models"]]
    assert any(g["code"] == "MODEL_DIFFERS" for g in data["gaps"])
    assert data["can_compile"] is False
    assert _compile(client, coverage_case, data["input_hash"]).status_code == 409


def test_task_definition_content_invalidates_old_preview(client, coverage_case):
    p, a, ids = coverage_case
    with SessionLocal() as db:
        task = ProcessTaskDefinition(
            activity_id=a["id"],
            position_id=ids["position"],
            code="JD-TASK",
            name="接收订单",
            description="核对订单",
        )
        db.add(task)
        db.commit()
        tid = task.id
    _fixed_model(coverage_case)
    data = preview(client, coverage_case)
    with SessionLocal() as db:
        task = db.get(ProcessTaskDefinition, tid)
        task.name = "批准付款"
        task.description = "审批付款"
        db.commit()
    newer = preview(client, coverage_case)
    assert data["input_hash"] != newer["input_hash"]
    assert _compile(client, coverage_case, data["input_hash"]).status_code == 409


def test_role_only_ambiguity_still_reports_unmapped_role(client, coverage_case):
    from app.models.user import User

    p, a, ids = coverage_case
    _raci(client, coverage_case, activity_id=a["id"])
    client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": "n1",
                    "name": "仅角色活动",
                    "node_type": "TASK",
                    "process_arch_id": a["id"],
                }
            ],
            "edges": [],
        },
    )
    with SessionLocal() as db:
        db.get(User, ids["users"][1]).position_id = ids["other"]
        db.commit()
    data = _coverage(client, coverage_case)
    assert any(
        r["role_id"] == ids["role"] and r["code"] == "UNMAPPED_ROLE" for r in data["unmapped_roles"]
    )


def test_description_source_link_uses_real_route_and_fixed_basis(client, coverage_case):
    _fixed_model(coverage_case)
    data = preview(client, coverage_case)
    activity = data["manifest"]["coverage"]["activities"][0]
    assert activity["designer_url"].startswith("http://testserver/#designer?")
    assert f"basis={activity['model_version_id']}" in activity["designer_url"]
