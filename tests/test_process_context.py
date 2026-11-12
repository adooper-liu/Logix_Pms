"""M3原章程与SIPOC交接的身份、修订和确认。"""

from uuid import uuid4

API = "/api/v1"


def process(client, code="L3-032"):
    row = next(row for row in client.get(f"{API}/process-map/flat").json() if row["code"] == code)
    if not row["owner_user_id"]:
        user = client.get(f"{API}/auth/me").json()
        updated = client.patch(f"{API}/process-map/{row['id']}", json={"owner_user_id": user["id"]})
        assert updated.status_code == 200, updated.text
        row = updated.json()
    return row


def charter_body(client, pid):
    users = client.get(f"{API}/start/charter-options").json()["users"]
    return {
        "process_id": pid,
        "purpose": "客户按期收到可用结果",
        "starts_at": "接到合格请求",
        "ends_at": "客户确认接收",
        "in_scope": "请求及交付",
        "out_of_scope": "其他产品",
        "stop_condition": "风险超限升级",
        "sponsor_user_id": users[0]["id"],
    }


def test_charter_options_only_offer_active_sponsors(client):
    from app.core.database import SessionLocal
    from app.models.user import User

    listed = client.get(f"{API}/start/charter-options").json()["users"]
    with SessionLocal() as db:
        assert all(db.get(User, row["id"]).is_active for row in listed)


def test_charter_details_revision_and_legacy_preservation(client):
    proc = process(client)
    path = f"{API}/start/charters/{proc['id']}"
    before = client.get(path)
    assert before.status_code == 200, before.text
    data = before.json()
    assert data["owner_user_id"] == proc["owner_user_id"]
    body = charter_body(client, proc["id"])
    body.update(
        expected_revision=data["revision"],
        details={
            "customer": "内部采购客户",
            "customer_result": "完整并可追溯的需求",
            "resource_commitment": "采购与财务各投入半天",
            "review_due": "2027-01-31",
        },
    )
    saved = client.put(path, json=body)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert out["revision"] == data["revision"] + 1
    assert out["details"]["customer"] == "内部采购客户"
    assert "已批准" not in out["verification_label"]
    assert client.put(path, json=body).status_code == 409
    legacy = charter_body(client, proc["id"])
    legacy["purpose"] = "旧入口修改范围"
    assert client.post(f"{API}/start/charters", json=legacy).status_code == 200
    after = client.get(path).json()
    assert after["details"] == out["details"]
    assert after["revision"] == out["revision"] + 1


def test_charter_rejects_bad_identity_and_readonly(client, viewer_client):
    proc = process(client)
    body = charter_body(client, proc["id"])
    body.update(expected_revision=0, details={"objective_id": 99999999})
    assert viewer_client.put(f"{API}/start/charters/{proc['id']}", json=body).status_code == 403
    assert client.get(f"{API}/start/charters/99999999").status_code == 404
    current = client.get(f"{API}/start/charters/{proc['id']}").json()
    body["expected_revision"] = current["revision"]
    assert client.put(f"{API}/start/charters/{proc['id']}", json=body).status_code == 400
    l4 = next(row for row in client.get(f"{API}/process-map/flat").json() if row["level"] == 4)
    assert client.get(f"{API}/start/charters/{l4['id']}").status_code == 400


def handoff_body(client):
    sender = process(client)
    receiver = process(client)
    admin = client.get(f"{API}/auth/me").json()
    users = client.get(f"{API}/auth/users").json()
    owner = next(row for row in users if row["username"] == "chen")
    return {
        "process_id": sender["id"],
        "values": {
            "supplier": "采购",
            "input": "已核需求",
            "process": "收集到交付",
            "output": "合格需求单",
            "customer": "询价团队",
        },
        "handoff": {
            "receiver_process_id": receiver["id"],
            "provider_user_id": admin["id"],
            "receiver_user_id": owner["id"],
            "quality": "必填项完整",
            "timing": "接到需求后2工作日",
            "exception_path": "缺料升级Owner",
        },
    }


def test_sipoc_handoff_confirmation_is_personal_and_versioned(client, owner_client):
    body = handoff_body(client)
    response = client.post(f"{API}/tools/SIPOC/sheets", json=body)
    assert response.status_code == 201, response.text
    saved = response.json()
    assert saved["handoff"]["receiver_process_id"] == body["handoff"]["receiver_process_id"]
    assert saved["template_version_id"]
    assert saved["confirmation_label"] == "待双方确认"
    path = f"{API}/tools/SIPOC/sheets/{saved['id']}"
    assert client.get(path).status_code == 200
    confirmation = {
        "side": "receiver",
        "decision": "ACCEPT",
        "evidence": "核对输入质量/时限及例外后接收",
        "expected_revision": 0,
    }
    assert client.post(path + "/confirm", json=confirmation).status_code == 403
    accepted = owner_client.post(path + "/confirm", json=confirmation)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["confirmation_label"] == "待提供方确认"
    assert owner_client.post(path + "/confirm", json=confirmation).status_code == 409
    confirmation.update(side="provider", expected_revision=1)
    both = client.post(path + "/confirm", json=confirmation)
    assert both.status_code == 200, both.text
    assert both.json()["confirmation_label"] == "双方已确认"
    assert both.json()["fields"] == saved["fields"]
    assert both.json()["handoff"]["confirmations"]["receiver"]["at"].endswith("+00:00")
    assert both.json()["revision"] == 2


def test_handoff_rejects_invalid_refs_and_non_sipoc(client):
    body = handoff_body(client)
    body["handoff"]["receiver_process_id"] = 99999999
    assert client.post(f"{API}/tools/SIPOC/sheets", json=body).status_code == 400
    body = handoff_body(client)
    assert client.post(f"{API}/tools/BPMN/sheets", json=body).status_code == 400


def test_handoff_rejection_and_process_card_summary(client, owner_client):
    body = handoff_body(client)
    saved = client.post(f"{API}/tools/SIPOC/sheets", json=body).json()
    assert "handoff" in saved
    path = f"{API}/tools/SIPOC/sheets/{saved['id']}/confirm"
    rejected = owner_client.post(
        path,
        json={
            "side": "receiver",
            "decision": "REJECT",
            "evidence": "质量条件不充分",
            "expected_revision": 0,
        },
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["confirmation_label"] == "存在异议"
    card = client.get(f"{API}/process-card/{body['handoff']['receiver_process_id']}").json()
    assert any(row["id"] == saved["id"] for row in card["handoffs"])


def test_handoff_project_visibility_and_cycle(client, viewer_client):
    from app.core.database import SessionLocal
    from app.models.project import Project

    body = handoff_body(client)
    body["handoff"]["receiver_process_id"] = body["process_id"]
    created = client.post(
        f"{API}/projects",
        json={
            "name": "M3范围-" + uuid4().hex[:8],
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": body["process_id"],
        },
    )
    project = created.json()["id"]
    try:
        with SessionLocal() as db:
            db.get(Project, project).org_unit_id = 1
            db.commit()
        body["project_id"] = project
        saved = client.post(f"{API}/tools/SIPOC/sheets", json=body)
        assert saved.status_code == 201, saved.text
        sid = saved.json()["id"]
        assert viewer_client.get(f"{API}/tools/SIPOC/sheets/{sid}").status_code == 404
        other = process(client)
        body["process_id"] = other["id"]
        assert client.post(f"{API}/tools/SIPOC/sheets", json=body).status_code == 201
        readonly = viewer_client.post(
            f"{API}/tools/SIPOC/sheets/{sid}/confirm",
            json={
                "side": "provider",
                "decision": "ACCEPT",
                "evidence": "不能越权",
                "expected_revision": 0,
            },
        )
        assert readonly.status_code == 403
    finally:
        client.delete(f"{API}/projects/{project}")


def test_charter_document_scope_and_dates(client, viewer_client):
    from datetime import date

    from app.core.database import SessionLocal
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion

    proc = process(client)
    with SessionLocal() as db:
        doc = ProcessDocument(
            process_id=proc["id"],
            code="M3-" + uuid4().hex[:8],
            title="原授权依据",
            category="POLICY",
            org_unit_id=1,
        )
        db.add(doc)
        db.flush()
        version = ProcessDocumentVersion(
            document_id=doc.id, version_label="1.0", status="EFFECTIVE", valid_to=date(2001, 1, 1)
        )
        db.add(version)
        db.commit()
        vid = version.id
        did = doc.id
    try:
        path = f"{API}/start/charters/{proc['id']}"
        before = client.get(path).json()
        body = charter_body(client, proc["id"])
        body.update(expected_revision=before["revision"], details={"mandate_version_id": vid})
        assert client.put(path, json=body).status_code == 400, "到期标准不能作为现行授权依据"
    finally:
        with SessionLocal() as db:
            db.delete(db.get(ProcessDocumentVersion, vid))
            db.delete(db.get(ProcessDocument, did))
            db.commit()


def test_charter_private_reference_and_retained_history(client, viewer_client):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.models.startup import ProcessCharter

    proc = process(client)
    with SessionLocal() as db:
        doc = ProcessDocument(
            process_id=proc["id"],
            code="PRIVATE-" + uuid4().hex[:8],
            title="私有依据",
            category="POLICY",
            org_unit_id=1,
        )
        db.add(doc)
        db.flush()
        version = ProcessDocumentVersion(
            document_id=doc.id, version_label="1.0", status="EFFECTIVE"
        )
        db.add(version)
        db.commit()
        vid = version.id
        did = doc.id
    path = f"{API}/start/charters/{proc['id']}"
    try:
        body = charter_body(client, proc["id"])
        body.update(
            expected_revision=client.get(path).json()["revision"],
            details={"mandate_version_id": vid, "verification_evidence": "受限核验内容"},
        )
        assert client.put(path, json=body).status_code == 200
        assert viewer_client.get(path).status_code == 404, "不可见文件不能从章程泄漏"
        with SessionLocal() as db:
            db.get(ProcessDocumentVersion, vid).status = "SUPERSEDED"
            db.commit()
        body["expected_revision"] += 1
        body["purpose"] = "保留历史引用修订客户结果"
        changed = client.put(path, json=body)
        assert changed.status_code == 200, changed.text
        assert "待复核" in changed.json()["reference_label"]
    finally:
        with SessionLocal() as db:
            row = db.scalar(select(ProcessCharter).where(ProcessCharter.process_id == proc["id"]))
            row.details = {}
            db.delete(db.get(ProcessDocumentVersion, vid))
            db.delete(db.get(ProcessDocument, did))
            db.commit()


def test_charter_objective_must_use_original_process_link(client):
    proc = process(client)
    created = client.post(
        f"{API}/strategy/objectives", json={"name": "无关目标-" + uuid4().hex[:8], "year": 2026}
    )
    objective = created.json()["id"]
    try:
        path = f"{API}/start/charters/{proc['id']}"
        body = charter_body(client, proc["id"])
        body.update(
            expected_revision=client.get(path).json()["revision"],
            details={"objective_id": objective},
        )
        assert client.put(path, json=body).status_code == 400
        assert (
            client.post(
                f"{API}/strategy/objectives/{objective}/links", json={"process_id": proc["id"]}
            ).status_code
            == 201
        )
        assert client.put(path, json=body).status_code == 200
    finally:
        client.delete(f"{API}/strategy/objectives/{objective}")


def test_private_sheet_cannot_leak_through_card_summary(client, viewer_client):
    from app.core.database import SessionLocal
    from app.models.project import Project

    body = handoff_body(client)
    created = client.post(
        f"{API}/projects",
        json={
            "name": "私有交接-" + uuid4().hex[:8],
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": body["process_id"],
        },
    )
    project = created.json()["id"]
    try:
        with SessionLocal() as db:
            db.get(Project, project).org_unit_id = 1
            db.commit()
        body["project_id"] = project
        saved = client.post(f"{API}/tools/SIPOC/sheets", json=body).json()
        card = viewer_client.get(f"{API}/process-card/{body['process_id']}").json()
        assert not any(row["id"] == saved["id"] for row in card["handoffs"])
        assert not any(row["id"] == saved["id"] for row in card["sheets"]), "受限方法摘要泄漏"
    finally:
        client.delete(f"{API}/projects/{project}")


def test_sheet_rejects_template_change_during_fill(client):
    from app.core.database import SessionLocal
    from app.models.tool_template import ToolTemplateVersion

    form = client.get(f"{API}/tools/SIPOC/sheet-form").json()
    vid = form["template_version_id"]
    with SessionLocal() as db:
        db.get(ToolTemplateVersion, vid).status = "SUPERSEDED"
        db.commit()
    try:
        body = handoff_body(client)
        body["template_version_id"] = vid
        assert client.post(f"{API}/tools/SIPOC/sheets", json=body).status_code == 409
    finally:
        with SessionLocal() as db:
            db.get(ToolTemplateVersion, vid).status = "EFFECTIVE"
            db.commit()


def test_charter_audit_keeps_before_and_after(client):
    import json

    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.user import AuditLog

    proc = process(client)
    path = f"{API}/start/charters/{proc['id']}"
    original = client.get(path)
    assert original.status_code == 200
    body = charter_body(client, proc["id"])
    body.update(
        expected_revision=original.json()["revision"],
        details={"customer": "记录-" + uuid4().hex[:8]},
    )
    assert client.put(path, json=body).status_code == 200
    with SessionLocal() as db:
        row = db.scalar(
            select(AuditLog)
            .where(AuditLog.entity_type == "process_charter", AuditLog.entity_id == proc["id"])
            .order_by(AuditLog.id.desc())
        )
        entry = json.loads(row.summary)
        assert entry["before"]["revision"] == original.json()["revision"]
        assert entry["after"]["details"]["customer"] == body["details"]["customer"]
