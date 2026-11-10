"""岗位文档复用容器，不能冒充流程来源或混入旧列表。"""

from uuid import uuid4

import pytest
from sqlalchemy import delete, text
from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.models.org import Position
from app.models.process_document import ProcessDocument

API = "/api/v1"


@pytest.fixture
def position_document(client):
    with SessionLocal() as db:
        pos = Position(code="JD-" + uuid4().hex[:8], name="职责岗位")
        db.add(pos)
        db.flush()
        doc = ProcessDocument(
            scope="POSITION",
            position_id=pos.id,
            code="JD-" + uuid4().hex[:8],
            title="岗位责任书",
            category="JOB_DESCRIPTION",
        )
        db.add(doc)
        db.commit()
        ids = (pos.id, doc.id)
    yield ids
    with SessionLocal() as db:
        db.execute(delete(ProcessDocument).where(ProcessDocument.id == ids[1]))
        db.execute(delete(Position).where(Position.id == ids[0]))
        db.commit()


def test_position_document_not_in_default_process_list(client, position_document):
    pid, did = position_document
    rows = client.get(f"{API}/process-documents").json()
    assert did not in {r["id"] for r in rows}
    detail = client.get(f"{API}/process-documents/{did}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["document_scope"] == "POSITION"
    assert detail.json()["position_id"] == pid
    assert detail.json()["process_id"] is None
    assert client.delete(f"{API}/positions/{pid}").status_code == 409


def test_scope_requires_exactly_one_subject(client):
    with SessionLocal() as db:
        # SQL-level check must reject unknown subject without relying on Pydantic.
        with pytest.raises(IntegrityError):
            db.execute(
                text(
                    "INSERT INTO process_document (scope, code, title, category, level, language, variation_policy, is_active, created_at, updated_at) VALUES ('POSITION','BAD-SCOPE','bad','JOB_DESCRIPTION','PROCESS','zh-CN','LOCKED',true,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            db.flush()
        db.rollback()


def test_position_document_rejected_as_process_source(client, position_document):
    from app.services import process_document
    from app.services.process_scope import is_document_applicable

    with SessionLocal() as db:
        document = db.get(ProcessDocument, position_document[1])
        with pytest.raises(process_document.ProcessDocumentError):
            process_document.require_process_document(document)
        # Project without process must not treat NULL subject as universal.
        assert is_document_applicable(db, document.process_id, None) is False


def test_position_document_download_and_history_enforce_scope(
    client, viewer_client, position_document
):
    from app.models.org import OrgUnit
    from app.models.process_document import ProcessDocumentVersion

    pid, did = position_document
    with SessionLocal() as db:
        org = OrgUnit(code="JDSCOPE-" + str(pid), name="不可见部门", type="DEPARTMENT")
        db.add(org)
        db.flush()
        org.path = f"/{org.id}/"
        oid = org.id
        db.get(Position, pid).org_unit_id = oid
        version = ProcessDocumentVersion(
            document_id=did,
            version_label="1.0",
            source_kind="COMPILED",
            compile_manifest={"kind": "JOB_DESCRIPTION"},
        )
        db.add(version)
        db.commit()
        vid = version.id
    try:
        for path in [
            f"/{did}",
            f"/{did}/versions",
            f"/{did}/versions/{vid}/download",
            f"/{did}/versions/{vid}/preview",
        ]:
            assert viewer_client.get(f"{API}/process-documents{path}").status_code == 404
        assert (
            client.post(
                f"{API}/process-documents/{did}/versions/upload",
                data={"version_label": "1.1"},
                files={"file": ("fake.txt", b"replace generated file", "text/plain")},
            ).status_code
            == 400
        )
    finally:
        with SessionLocal() as db:
            db.execute(
                delete(ProcessDocumentVersion).where(ProcessDocumentVersion.document_id == did)
            )
            db.get(Position, pid).org_unit_id = None
            db.flush()
            db.delete(db.get(OrgUnit, oid))
            db.commit()
