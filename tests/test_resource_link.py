"""P1 原资源引用：不复制表单/规则，不允许异流程与只读写入。"""

from uuid import uuid4

import pytest

API = "/api/v1"


@pytest.fixture
def resource_case(client):
    suffix = uuid4().hex[:8]
    p = client.post(
        f"{API}/process-map", json={"code": f"RL-{suffix}", "name": "资源测试", "level": 3}
    ).json()
    a = client.post(
        f"{API}/process-map",
        json={"code": f"RLA-{suffix}", "name": "资源活动", "level": 4, "parent_id": p["id"]},
    ).json()
    response = client.put(
        f"{API}/processes/{p['id']}/design",
        json={
            "nodes": [
                {"node_key": "a", "name": "执行", "node_type": "TASK", "process_arch_id": a["id"]}
            ],
            "edges": [],
        },
    )
    assert response.status_code == 200, response.text
    form = client.post(
        f"{API}/execution/forms",
        json={"process_id": p["id"], "node_key": "a", "name": "原记录", "fields": []},
    )
    assert form.status_code == 201, form.text
    yield p, a, form.json()
    from app.core.database import SessionLocal
    from app.models.resource_link import ActivityResourceLink

    with SessionLocal() as db:
        db.query(ActivityResourceLink).filter_by(activity_id=a["id"]).delete()
        db.commit()
    client.delete(f"{API}/execution/forms/{form.json()['id']}")
    assert client.delete(f"{API}/process-map/{p['id']}").status_code == 200


def test_link_original_form_idempotent_and_deactivate(resource_case, client, viewer_client):
    p, a, form = resource_case
    path = f"{API}/processes/{p['id']}/resource-links"
    data = {"activity_id": a["id"], "resource_type": "FORM", "ref_id": form["id"], "node_key": "a"}
    saved = client.post(path, json=data)
    assert saved.status_code == 201, saved.text
    row = saved.json()
    assert row["ref_key"] == f"FORM:{form['id']}"
    assert row["resource_type_label"] == "任务表单"
    assert client.post(path, json=data).json()["id"] == row["id"]
    assert client.get(path).json()[0]["source_valid"] is True
    assert viewer_client.post(path, json=data).status_code == 403
    assert viewer_client.delete(path + f"/{row['id']}").status_code == 403
    options = client.get(
        f"{API}/processes/{p['id']}/resource-link-options?activity_id={a['id']}&node_key=a"
    )
    assert options.status_code == 200, options.text
    assert any(
        r["ref_id"] == form["id"] and r["resource_type"] == "FORM"
        for r in options.json()["options"]
    )
    assert client.delete(path + f"/{row['id']}").status_code == 200
    assert client.get(path).json() == []
    assert client.get(f"{API}/execution/forms?process_id={p['id']}").json()[0]["id"] == form["id"]


def test_resource_validation_and_external_key(resource_case, client):
    p, a, form = resource_case
    path = f"{API}/processes/{p['id']}/resource-links"
    base = {"activity_id": a["id"], "resource_type": "FORM", "ref_id": form["id"]}
    assert client.post(path, json={**base, "node_key": "missing"}).status_code == 400
    assert client.post(path, json={**base, "ref_id": 99999999}).status_code == 400
    assert client.post(path, json={**base, "ref_key": "FORM:9999"}).status_code == 400
    foreign = next(
        row
        for row in client.get(f"{API}/process-map/flat").json()
        if row["level"] == 4 and row["parent_id"] != p["id"]
    )
    assert client.post(path, json={**base, "activity_id": foreign["id"]}).status_code == 400
    assert (
        client.post(
            path, json={"activity_id": a["id"], "resource_type": "EQUIPMENT", "ref_key": "bad"}
        ).status_code
        == 400
    )
    eq = client.post(
        path,
        json={"activity_id": a["id"], "resource_type": "EQUIPMENT", "ref_key": "EQUIP:PUMP-01"},
    )
    assert eq.status_code == 201, eq.text
    assert "登记" in eq.json()["source_note"]


def test_node_specific_form_cannot_bind_other_activity(resource_case, client):
    p, a, form = resource_case
    sibling = client.post(
        f"{API}/process-map",
        json={
            "code": "OTHER-" + uuid4().hex[:8],
            "name": "兄弟活动",
            "level": 4,
            "parent_id": p["id"],
        },
    ).json()
    response = client.post(
        f"{API}/processes/{p['id']}/resource-links",
        json={"activity_id": sibling["id"], "resource_type": "FORM", "ref_id": form["id"]},
    )
    assert response.status_code == 400, response.text


def test_private_process_resource_read_does_not_expose_content(
    resource_case, client, viewer_client
):
    from app.core.database import SessionLocal
    from app.models.org import OrgUnit
    from app.models.process import ProcessArch

    p, a, form = resource_case
    with SessionLocal() as db:
        org = OrgUnit(
            code="PRIVATE-" + uuid4().hex[:8], name="来源组织", type="DEPARTMENT", path="/private/"
        )
        db.add(org)
        db.flush()
        process = db.get(ProcessArch, p["id"])
        process.org_unit_id = org.id
        db.commit()
        oid = org.id
    try:
        path = f"{API}/processes/{p['id']}/resource-links"
        response = client.post(
            path,
            json={
                "activity_id": a["id"],
                "resource_type": "FORM",
                "ref_id": form["id"],
                "note": "不应泄露的业务备注",
            },
        )
        assert response.status_code == 201, response.text
        rows = viewer_client.get(path).json()
        assert rows[0]["source_valid"] is False
        assert rows[0]["source_label"] == "受限来源"
        assert rows[0]["note"] is None
        assert "不应泄露的业务备注" not in str(rows)
        opts = viewer_client.get(
            f"{API}/processes/{p['id']}/resource-link-options?activity_id={a['id']}"
        ).json()
        assert not opts["options"]
    finally:
        with SessionLocal() as db:
            db.get(ProcessArch, p["id"]).org_unit_id = None
            db.delete(db.get(OrgUnit, oid))
            db.commit()


def test_sop_resource_is_not_a_record_carrier(resource_case, client):
    from sqlalchemy import select

    from app.core.database import SessionLocal
    from app.models.org import Position
    from app.models.process import ProcessModelVersion
    from app.models.process_document import ProcessDocument, ProcessDocumentVersion
    from app.models.workload import WorkMeasurementStandard

    p, a, form = resource_case
    assert client.delete(f"{API}/execution/forms/{form['id']}").status_code == 200
    with SessionLocal() as db:
        position = Position(code="CARRIER-" + uuid4().hex[:8], name="记录岗位")
        db.add(position)
        db.flush()
        version = db.scalar(
            select(ProcessModelVersion).where(ProcessModelVersion.process_id == p["id"])
        )
        snap = dict(version.snapshot)
        snap["nodes"] = [{**n, "owner_position_id": position.id} for n in snap["nodes"]]
        version.snapshot = snap
        standard = WorkMeasurementStandard(
            code="WC-" + uuid4().hex[:8],
            name="标准",
            activity_id=a["id"],
            position_id=position.id,
            status="VERIFIED",
            standard_minutes=5,
        )
        document = ProcessDocument(
            process_id=p["id"], code="SOP-" + uuid4().hex[:8], title="不是记录载体", category="SOP"
        )
        document.versions = [ProcessDocumentVersion(version_label="1.0", status="EFFECTIVE")]
        db.add_all([standard, document])
        db.commit()
        did = document.id
        sid = standard.id
        posid = position.id
    try:
        response = client.post(
            f"{API}/processes/{p['id']}/resource-links",
            json={"activity_id": a["id"], "resource_type": "DOCUMENT", "ref_id": did},
        )
        assert response.status_code == 201, response.text
        data = client.get(f"{API}/processes/{p['id']}/binding-readiness").json()
        facet = next(f for f in data["activities"][0]["facets"] if f["key"] == "RESOURCE")
        assert facet["status"] == "PARTIAL"
        assert any("载体" in gap for gap in facet["gaps"])
    finally:
        with SessionLocal() as db:
            db.delete(db.get(WorkMeasurementStandard, sid))
            db.delete(db.get(ProcessDocument, did))
            db.commit()
            db.delete(db.get(Position, posid))
            db.commit()


def test_source_deleted_is_explicitly_stale(resource_case, client):
    p, a, form = resource_case
    path = f"{API}/processes/{p['id']}/resource-links"
    saved = client.post(
        path, json={"activity_id": a["id"], "resource_type": "FORM", "ref_id": form["id"]}
    )
    assert saved.status_code == 201, saved.text
    assert client.delete(f"{API}/execution/forms/{form['id']}").status_code == 200
    row = client.get(path).json()[0]
    assert row["source_valid"] is False
    assert row["source_status"] == "STALE"
    readiness = client.get(f"{API}/processes/{p['id']}/binding-readiness").json()
    assert any("失效" in gap for f in readiness["activities"][0]["facets"] for gap in f["gaps"])
