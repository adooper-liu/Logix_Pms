"""责任书预览保持来源、身份与确定性，不写业务对象。"""

import hashlib

import pytest
from sqlalchemy import func, select
from test_position_coverage import coverage_case as shared_coverage_case

from app.core.database import SessionLocal
from app.models.org import Position
from app.models.process import ProcessModelVersion
from app.models.process_document import ProcessDocumentVersion
from app.models.user import AuditLog, User

API = "/api/v1"
coverage_case = pytest.fixture(name="coverage_case")(shared_coverage_case.__wrapped__)


def preview(client, case):
    response = client.post(
        f"{API}/positions/{case[2]['position']}/job-description/preview",
        json={"period": "2026-10-01"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_is_read_only_deterministic_and_escapes_sources(client, coverage_case):
    with SessionLocal() as db:
        db.get(Position, coverage_case[2]["position"]).name = "<script>alert(1)</script>"
        db.commit()
        before = [
            db.scalar(select(func.count()).select_from(cls))
            for cls in [AuditLog, ProcessModelVersion, ProcessDocumentVersion]
        ]
    a = preview(client, coverage_case)
    b = preview(client, coverage_case)
    assert a["input_hash"] == b["input_hash"]
    assert a["content_hash"] == b["content_hash"]
    assert "<script>alert(1)</script>" not in a["preview_html"]
    assert "&lt;script&gt;" in a["preview_html"]
    assert "&quot;activity_id&quot;" not in a["preview_html"]
    assert "节点责任岗位" in a["preview_html"]
    assert hashlib.sha256(a["preview_html"].encode()).hexdigest() == a["content_hash"]
    with SessionLocal() as db:
        assert before == [
            db.scalar(select(func.count()).select_from(cls))
            for cls in [AuditLog, ProcessModelVersion, ProcessDocumentVersion]
        ]


def test_preview_lists_all_sources_and_missing_bindings(client, coverage_case):
    data = preview(client, coverage_case)
    assert data["kind"] == "JOB_DESCRIPTION"
    assert data["can_compile"] is False
    assert "无已验证标准工时" in data["preview_html"]
    assert str(coverage_case[0]["id"]) in data["preview_html"]
    assert "n1" in data["preview_html"]
    assert any(g["code"] == "MODEL_NOT_PUBLISHED" for g in data["gaps"])
    assert [s["title"] for s in data["sections"]] == [
        "岗位与范围",
        "参与流程与活动",
        "职责与协作",
        "工作量参考",
        "指标与控制",
        "来源与缺口",
    ]


def test_preview_changes_when_role_membership_or_source_changes(client, coverage_case):
    a = preview(client, coverage_case)
    with SessionLocal() as db:
        db.get(Position, coverage_case[2]["position"]).description = "新的岗位边界"
        db.commit()
    b = preview(client, coverage_case)
    assert a["input_hash"] != b["input_hash"]
    with SessionLocal() as db:
        db.get(User, coverage_case[2]["users"][0]).position_id = coverage_case[2]["other"]
        db.commit()
    # 未参与职责的人员不是编译来源，不因无关人员变化重开版本。
    assert preview(client, coverage_case)["input_hash"] == b["input_hash"]


def test_preview_separates_draft_and_published_model(client, coverage_case):
    from app.models.process import ProcessArch
    from app.services import binding_snapshot

    p, _a, _ids = coverage_case
    with SessionLocal() as db:
        current = db.scalar(
            select(ProcessModelVersion).where(ProcessModelVersion.process_id == p["id"])
        )
        current.status = "PUBLISHED"
        current.binding_snapshot = binding_snapshot.capture(
            db, db.get(ProcessArch, p["id"]), current
        )
        db.get(ProcessArch, p["id"]).published_model_version = current.version
        db.commit()
        vid = current.id
    response = client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {
                    "node_key": "n1",
                    "name": "仅工作版新活动名称",
                    "node_type": "TASK",
                    "process_arch_id": coverage_case[1]["id"],
                    "owner_position_id": coverage_case[2]["position"],
                }
            ],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    data = preview(client, coverage_case)
    assert data["can_compile"] is False
    assert data["manifest"]["models"][0]["model_version_id"] == vid
    assert any(g["code"] == "MODEL_DIFFERS" for g in data["gaps"])
    # 发布依据的节点应保留；不能用最新工作版代替已发布版绑定。
    assert data["manifest"]["published_bindings"][0]["nodes"][1]["node_key"] == "n2"


def test_preview_cannot_leak_restricted_sources(client, viewer_client, coverage_case):
    from sqlalchemy import delete

    from app.models.org import OrgUnit
    from app.models.workload import WorkMeasurementStandard

    p, a, ids = coverage_case
    with SessionLocal() as db:
        org = OrgUnit(code="JDORG-" + str(a["id"]), name="隐藏组织", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        orgid = org.id
        db.add(
            WorkMeasurementStandard(
                code="JDSECRET-" + str(a["id"]),
                name="保密工时",
                activity_id=a["id"],
                position_id=ids["position"],
                org_unit_id=orgid,
                standard_minutes=10,
                monthly_frequency=10,
                status="VERIFIED",
            )
        )
        db.commit()
    try:
        data = preview(viewer_client, coverage_case)
        assert "保密工时" not in data["preview_html"]
        assert data["can_compile"] is False
        assert any(g["code"] == "SOURCE_RESTRICTED" for g in data["gaps"])
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(WorkMeasurementStandard).where(WorkMeasurementStandard.org_unit_id == orgid)
            )
            db.delete(db.get(OrgUnit, orgid))
            db.commit()


def _fixed_model(case):
    from app.models.process import ProcessArch
    from app.services import binding_snapshot

    with SessionLocal() as db:
        process = db.get(ProcessArch, case[0]["id"])
        version = db.scalar(
            select(ProcessModelVersion).where(ProcessModelVersion.process_id == process.id)
        )
        version.status = "PUBLISHED"
        version.binding_snapshot = binding_snapshot.capture(db, process, version)
        process.published_model_version = version.version
        db.commit()


def _compile(client, case, digest):
    return client.post(
        f"{API}/positions/{case[2]['position']}/job-descriptions",
        json={
            "period": "2026-10-01",
            "expected_input_hash": digest,
        },
    )


def _remove_generated(case):
    from sqlalchemy import delete

    from app.models.process_document import CompiledAssetComponent, ProcessDocument

    with SessionLocal() as db:
        docs = list(
            db.scalars(
                select(ProcessDocument).where(ProcessDocument.position_id == case[2]["position"])
            ).all()
        )
        for doc in docs:
            for version in doc.versions:
                db.execute(
                    delete(CompiledAssetComponent).where(
                        CompiledAssetComponent.document_version_id == version.id
                    )
                )
            db.delete(doc)
        db.commit()


def test_compile_requires_preview_hash_and_reuses_identical_version(client, coverage_case):
    _fixed_model(coverage_case)
    data = preview(client, coverage_case)
    assert data["can_compile"] is True
    try:
        stale = _compile(client, coverage_case, "0" * 64)
        assert stale.status_code == 409
        created = _compile(client, coverage_case, data["input_hash"])
        assert created.status_code == 201, created.text
        again = _compile(client, coverage_case, data["input_hash"])
        assert again.status_code == 201, again.text
        assert again.json()["version_id"] == created.json()["version_id"]
        assert created.json()["status"] == "DRAFT"
        assert created.json()["content_hash"] == data["content_hash"]
    finally:
        _remove_generated(coverage_case)


def test_compile_viewer_forbidden_and_cross_position_not_found(
    client, viewer_client, coverage_case
):
    assert _compile(viewer_client, coverage_case, "0" * 64).status_code == 403
    assert (
        client.get(
            f"{API}/positions/{coverage_case[2]['position']}/job-descriptions/999999"
        ).status_code
        == 404
    )


def test_generic_transition_cannot_bypass_job_description_source_check(client, coverage_case):
    _fixed_model(coverage_case)
    data = preview(client, coverage_case)
    try:
        created = _compile(client, coverage_case, data["input_hash"])
        assert created.status_code == 201, created.text
        saved = created.json()
        with SessionLocal() as db:
            db.get(Position, coverage_case[2]["position"]).description = "岗位范围发生变化"
            db.commit()
        response = client.post(
            f"{API}/process-documents/{saved['document_id']}/versions/{saved['version_id']}/transition",
            json={"status": "IN_REVIEW"},
        )
        assert response.status_code == 409, response.text
        history = client.get(
            f"{API}/positions/{coverage_case[2]['position']}/job-descriptions/{saved['version_id']}"
        )
        assert history.status_code == 200, history.text
        assert history.json()["content_hash"] == data["content_hash"]
        assert "岗位范围发生变化" not in history.json()["preview_html"]
    finally:
        _remove_generated(coverage_case)


def test_three_positions_complete_existing_document_lifecycle(client, coverage_case):
    from test_position_coverage import _raci
    from test_publish_gate_bindings import complete_performance

    from app.models.execution import FormDefinition
    from app.models.workload import WorkMeasurementStandard

    p, a, ids = coverage_case
    _raci(client, coverage_case, activity_id=a["id"], raci="A")
    with SessionLocal() as db:
        db.add(
            WorkMeasurementStandard(
                code="JDS-" + str(a["id"]),
                name="验证工时",
                activity_id=a["id"],
                position_id=ids["position"],
                status="VERIFIED",
                standard_minutes=5,
            )
        )
        for key in ["n1", "n2"]:
            db.add(FormDefinition(process_id=p["id"], node_key=key, name=key + "记录", fields=[]))
        db.commit()
    complete_performance({"pid": p["id"], "aid": a["id"]})
    _fixed_model(coverage_case)
    try:
        created = _compile(client, coverage_case, preview(client, coverage_case)["input_hash"])
        assert created.status_code == 201, created.text
        saved = created.json()
        for status in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            response = client.post(
                f"{API}/process-documents/{saved['document_id']}/versions/{saved['version_id']}/transition",
                json={"status": status},
            )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == status
        detail = client.get(
            f"{API}/positions/{coverage_case[2]['position']}/job-descriptions/{saved['version_id']}"
        ).json()
        assert detail["manifest"]["rule_version"] == "job-description/v1"
        assert detail["status"] == "EFFECTIVE"
    finally:
        _remove_generated(coverage_case)
        from test_publish_gate_bindings import clean_documents

        clean_documents({"pid": p["id"], "aid": a["id"], "position": ids["position"]})
        with SessionLocal() as db:
            from sqlalchemy import delete

            db.execute(delete(FormDefinition).where(FormDefinition.process_id == p["id"]))
            db.commit()


def test_storage_or_transaction_failure_leaves_no_partial_version(
    client, coverage_case, monkeypatch
):
    from datetime import date
    from pathlib import Path

    from fastapi import HTTPException
    from sqlalchemy.exc import IntegrityError

    from app.core.config import settings
    from app.models.process_document import ProcessDocument
    from app.services import job_description
    from app.services import process_document as document_service

    _fixed_model(coverage_case)
    digest = preview(client, coverage_case)["input_hash"]
    before_files = set(Path(settings.attachment_dir).rglob("*.html"))

    def fail_create(*args, **kwargs):
        raise IntegrityError("injected version collision", {}, Exception("collision"))

    monkeypatch.setattr(document_service, "create_version", fail_create)
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.username == "admin"))
        with pytest.raises(HTTPException) as failure:
            job_description.compile(
                db,
                coverage_case[2]["position"],
                actor,
                date(2026, 10, 1),
                digest,
                application_url="http://testserver/",
            )
        assert failure.value.status_code == 409
        assert (
            db.scalar(
                select(ProcessDocument).where(
                    ProcessDocument.position_id == coverage_case[2]["position"]
                )
            )
            is None
        )
    assert set(Path(settings.attachment_dir).rglob("*.html")) == before_files


def test_role_change_and_retirement_do_not_rewrite_history(client, coverage_case):
    from test_position_coverage import _raci

    _raci(client, coverage_case, activity_id=coverage_case[1]["id"])
    _fixed_model(coverage_case)
    try:
        created = _compile(client, coverage_case, preview(client, coverage_case)["input_hash"])
        assert created.status_code == 201, created.text
        saved = created.json()
        with SessionLocal() as db:
            db.get(User, coverage_case[2]["users"][0]).position_id = coverage_case[2]["other"]
            db.commit()
        changed = preview(client, coverage_case)
        assert changed["input_hash"] != saved["manifest"]["input_hash"]
        moved = client.post(
            f"{API}/process-documents/{saved['document_id']}/versions/{saved['version_id']}/transition",
            json={"status": "IN_REVIEW"},
        )
        assert moved.status_code == 409
        retired = client.post(
            f"{API}/process-documents/{saved['document_id']}/versions/{saved['version_id']}/transition",
            json={"status": "RETIRED"},
        )
        assert retired.status_code == 200, retired.text
        detail = client.get(
            f"{API}/positions/{coverage_case[2]['position']}/job-descriptions/{saved['version_id']}"
        ).json()
        assert detail["content_hash"] == saved["content_hash"]
    finally:
        _remove_generated(coverage_case)
