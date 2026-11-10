"""P1 绑定快照固定、来源改变与旧依据不可覆盖。"""

from copy import deepcopy
from uuid import uuid4

import pytest

from app.core.database import SessionLocal
from app.models.process import ProcessModelVersion

API = "/api/v1"


@pytest.fixture
def snapshot_case(client):
    suffix = uuid4().hex[:8]
    p = client.post(
        f"{API}/process-map",
        json={"code": f"BS-{suffix}", "name": "绑定快照", "level": 3, "publish_policy": "direct"},
    ).json()
    a = client.post(
        f"{API}/process-map",
        json={"code": f"BSA-{suffix}", "name": "活动", "level": 4, "parent_id": p["id"]},
    ).json()
    payload = {
        "nodes": [
            {"node_key": "a", "name": "活动节点", "node_type": "TASK", "process_arch_id": a["id"]}
        ],
        "edges": [],
    }
    saved = client.put(f"{API}/processes/{p['id']}/design", json=payload)
    assert saved.status_code == 200, saved.text
    form = client.post(
        f"{API}/execution/forms",
        json={"process_id": p["id"], "node_key": "a", "name": "快照记录", "fields": []},
    ).json()
    yield p, a, form, payload, saved.json()
    from app.models.resource_link import ActivityResourceLink

    with SessionLocal() as db:
        db.query(ActivityResourceLink).filter_by(activity_id=a["id"]).delete()
        db.commit()
    client.delete(f"{API}/execution/forms/{form['id']}")
    assert client.delete(f"{API}/process-map/{p['id']}").status_code == 200


def _readiness(client, p):
    response = client.get(f"{API}/processes/{p['id']}/binding-readiness")
    assert response.status_code == 200, response.text
    return response.json()


def test_freeze_captures_once_and_changes_pending_then_stale(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    before = _readiness(client, p)
    assert before["consistency"] == "PENDING_CONFIRM"
    path = f"{API}/processes/{p['id']}/resource-links"
    link = client.post(
        path, json={"activity_id": a["id"], "resource_type": "FORM", "ref_id": form["id"]}
    )
    assert link.status_code == 201, link.text
    frozen = client.post(
        f"{API}/processes/{p['id']}/design/freeze",
        json={"expected_version": model["version"], "note": "固定绑定原依据"},
    )
    assert frozen.status_code == 200, frozen.text
    vid = frozen.json()["id"]
    with SessionLocal() as db:
        snapshot = deepcopy(db.get(ProcessModelVersion, vid).binding_snapshot)
    assert snapshot["activities"][str(a["id"])]["hash"]
    assert _readiness(client, p)["consistency"] == "CONFIRMED"
    changed = client.patch(f"{API}/execution/forms/{form['id']}", json={"name": "修订原记录"})
    assert changed.status_code == 200, changed.text
    assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"
    # 再固定不得覆盖旧快照，当前源更改不抹历史。
    repeated = client.post(
        f"{API}/processes/{p['id']}/design/freeze",
        json={"expected_version": model["version"], "note": "重复请求"},
    )
    assert repeated.status_code == 200, repeated.text
    with SessionLocal() as db:
        assert db.get(ProcessModelVersion, vid).binding_snapshot == snapshot
    assert client.delete(path + f"/{link.json()['id']}").status_code == 200
    assert _readiness(client, p)["consistency"] == "STALE"


def test_publish_snapshot_and_new_version_needs_confirmation(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    response = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "发布活动绑定依据",
            "self_publish_reason": "隔离合成验收确认由同一人发布原模型",
        },
    )
    assert response.status_code == 200, response.text
    versions = client.get(f"{API}/processes/{p['id']}/design/versions").json()
    with SessionLocal() as db:
        snap = deepcopy(db.get(ProcessModelVersion, versions[0]["id"]).binding_snapshot)
    assert snap is not None
    assert _readiness(client, p)["consistency"] == "CONFIRMED"
    payload["nodes"][0]["name"] = "新工作版"
    saved = client.put(
        f"{API}/processes/{p['id']}/design",
        json={**payload, "expected_version": response.json()["version"]},
    )
    assert saved.status_code == 200, saved.text
    assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"
    with SessionLocal() as db:
        assert db.get(ProcessModelVersion, versions[0]["id"]).binding_snapshot == snap


def test_node_evidence_and_objective_change_invalidate_binding(snapshot_case, client):
    from sqlalchemy import select

    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget
    from app.models.process import ProcessNode
    from app.models.strategy import ObjectiveProcessLink, StrategyObjective

    p, a, form, payload, model = snapshot_case
    published = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "合成证据版本发布",
            "self_publish_reason": "隔离合成测试确认原模型同人发布",
        },
    )
    assert published.status_code == 200, published.text
    with SessionLocal() as db:
        node = db.scalar(select(ProcessNode).where(ProcessNode.process_id == p["id"]))
        objective = StrategyObjective(
            code="OBJ-" + uuid4().hex[:8], name="原承接目标", year=2026, status="ACTIVE"
        )
        db.add(objective)
        db.flush()
        goal_link = ObjectiveProcessLink(objective_id=objective.id, process_id=p["id"])
        claim = EvidenceClaim(
            process_id=p["id"],
            claim="节点控制依据",
            claim_type="CONTROL",
            source_type="DOCUMENT_VERSION",
            method="DOCUMENTED",
            status="SUPPORTED",
            targets=[
                EvidenceClaimTarget(
                    target_type="NODE",
                    target_id=node.id,
                    model_version_id=published.json()["version_id"],
                )
            ],
        )
        db.add_all([goal_link, claim])
        db.commit()
        oid = objective.id
        cid = claim.id
        lid = goal_link.id
    try:
        # 在新模型版本固定当前来源。
        saved = client.put(
            f"{API}/processes/{p['id']}/design",
            json={**payload, "expected_version": published.json()["version"]},
        )
        assert saved.status_code == 200, saved.text
        assert (
            client.post(
                f"{API}/processes/{p['id']}/design/freeze",
                json={"expected_version": saved.json()["version"], "note": "固定当前目标证据"},
            ).status_code
            == 200
        )
        assert _readiness(client, p)["consistency"] == "CONFIRMED"
        with SessionLocal() as db:
            db.get(StrategyObjective, oid).target_value = 80
            db.commit()
        assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"
    finally:
        with SessionLocal() as db:
            db.delete(db.get(EvidenceClaim, cid))
            db.delete(db.get(ObjectiveProcessLink, lid))
            db.delete(db.get(StrategyObjective, oid))
            db.commit()


def test_published_node_claim_change_invalidates_current_snapshot(snapshot_case, client):
    from sqlalchemy import select

    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget
    from app.models.process import ProcessNode
    from app.models.tool_sheet import ToolSheet

    p, a, form, payload, model = snapshot_case
    published = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "节点证据基线",
            "self_publish_reason": "隔离合成测试确认原模型同人发布",
        },
    )
    assert published.status_code == 200, published.text
    vid = published.json()["version_id"]
    with SessionLocal() as db:
        node = db.scalar(select(ProcessNode).where(ProcessNode.process_id == p["id"]))
        sheet = ToolSheet(process_id=p["id"], tool_code="SIPOC", title="节点依据", fields=[])
        db.add(sheet)
        db.flush()
        sid = sheet.id
        claim = EvidenceClaim(
            process_id=p["id"],
            claim="当前节点控制",
            claim_type="CONTROL",
            source_type="TOOL_SHEET",
            source_id=sheet.id,
            method="DOCUMENTED",
            status="SUPPORTED",
            targets=[
                EvidenceClaimTarget(target_type="NODE", target_id=node.id, model_version_id=vid)
            ],
        )
        db.add(claim)
        db.flush()
        from app.services import binding_snapshot

        process = db.get(
            __import__("app.models.process", fromlist=["ProcessArch"]).ProcessArch, p["id"]
        )
        db.get(ProcessModelVersion, vid).binding_snapshot = binding_snapshot.capture(
            db, process, db.get(ProcessModelVersion, vid)
        )
        db.commit()
        cid = claim.id
    try:
        assert _readiness(client, p)["consistency"] == "CONFIRMED"
        with SessionLocal() as db:
            db.get(EvidenceClaim, cid).claim = "已变更的节点控制"
            db.commit()
        assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"
    finally:
        with SessionLocal() as db:
            db.delete(db.get(EvidenceClaim, cid))
            db.delete(db.get(ToolSheet, sid))
            db.commit()


def test_freeze_published_version_does_not_replace_release_basis(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    published = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "发布绑定基线",
            "self_publish_reason": "隔离合成测试同人发布固定依据",
        },
    )
    assert published.status_code == 200, published.text
    vid = published.json()["version_id"]
    with SessionLocal() as db:
        basis = deepcopy(db.get(ProcessModelVersion, vid).binding_snapshot)
    assert (
        client.patch(f"{API}/execution/forms/{form['id']}", json={"name": "发布后变化"}).status_code
        == 200
    )
    frozen = client.post(
        f"{API}/processes/{p['id']}/design/freeze",
        json={"expected_version": published.json()["version"], "note": "不得覆盖发布依据"},
    )
    assert frozen.status_code == 200, frozen.text
    with SessionLocal() as db:
        assert db.get(ProcessModelVersion, vid).binding_snapshot == basis
    assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"


def test_unchanged_invalid_frozen_source_is_not_new_publish_gate(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    linked = client.post(
        f"{API}/processes/{p['id']}/resource-links",
        json={"activity_id": a["id"], "resource_type": "FORM", "ref_id": form["id"]},
    )
    assert linked.status_code == 201, linked.text
    assert (
        client.patch(f"{API}/execution/forms/{form['id']}", json={"is_active": False}).status_code
        == 200
    )
    assert (
        client.post(
            f"{API}/processes/{p['id']}/design/freeze",
            json={"expected_version": model["version"], "note": "记录现存失效来源"},
        ).status_code
        == 200
    )
    response = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "来源未变化允许设计发布",
            "self_publish_reason": "隔离合成测试同人发布固定依据",
        },
    )
    assert response.status_code == 200, response.text
    assert _readiness(client, p)["consistency"] == "STALE"


def test_l4_binding_readiness_remains_supported(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    response = client.get(f"{API}/processes/{a['id']}/binding-readiness")
    assert response.status_code == 200, response.text
    assert response.json()["activities"][0]["activity_id"] == a["id"]


def test_evidence_source_content_change_and_deletion_invalidate(snapshot_case, client):
    from app.models.asset_graph import EvidenceClaim, EvidenceClaimTarget
    from app.models.tool_sheet import ToolSheet

    p, a, form, payload, model = snapshot_case
    with SessionLocal() as db:
        sheet = ToolSheet(
            process_id=p["id"], tool_code="SIPOC", title="原证据表", fields=[], revision=0
        )
        db.add(sheet)
        db.flush()
        claim = EvidenceClaim(
            process_id=p["id"],
            claim="活动控制",
            claim_type="CONTROL",
            source_type="TOOL_SHEET",
            source_id=sheet.id,
            source_hash="a" * 64,
            method="DOCUMENTED",
            status="SUPPORTED",
            targets=[EvidenceClaimTarget(target_type="ACTIVITY", target_id=a["id"])],
        )
        db.add(claim)
        db.commit()
        sid = sheet.id
        cid = claim.id
    try:
        assert (
            client.post(
                f"{API}/processes/{p['id']}/design/freeze",
                json={"expected_version": model["version"], "note": "固定证据来源"},
            ).status_code
            == 200
        )
        assert _readiness(client, p)["consistency"] == "CONFIRMED"
        with SessionLocal() as db:
            db.get(ToolSheet, sid).fields = [{"value": "来源已经变化"}]
            db.get(ToolSheet, sid).revision += 1
            db.commit()
        assert _readiness(client, p)["consistency"] == "PENDING_CONFIRM"
        with SessionLocal() as db:
            db.delete(db.get(ToolSheet, sid))
            db.commit()
        assert _readiness(client, p)["consistency"] == "STALE"
    finally:
        with SessionLocal() as db:
            db.delete(db.get(EvidenceClaim, cid))
            sheet = db.get(ToolSheet, sid)
            if sheet:
                db.delete(sheet)
            db.commit()


def test_frozen_changed_binding_cannot_be_overwritten_by_publish(snapshot_case, client):
    p, a, form, payload, model = snapshot_case
    assert (
        client.post(
            f"{API}/processes/{p['id']}/design/freeze",
            json={"expected_version": model["version"], "note": "固定"},
        ).status_code
        == 200
    )
    assert (
        client.patch(f"{API}/execution/forms/{form['id']}", json={"name": "不同依据"}).status_code
        == 200
    )
    response = client.post(
        f"{API}/processes/{p['id']}/design/publish",
        json={
            "expected_version": model["version"],
            "change_note": "不能覆盖旧冻结绑定",
            "self_publish_reason": "隔离合成验收确认由同一人发布原模型",
        },
    )
    assert response.status_code == 409, response.text
    assert "绑定" in response.text
