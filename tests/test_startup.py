"""九步启动状态：readiness 由现有数据自动计算。"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.authorization import AuthorizationRule
from app.models.enums import AuthorizationStatus, DeliverableStatus
from app.models.process import ProcessArch
from app.models.process_document import ProcessDocument, ProcessDocumentVersion
from app.models.user import User

API = "/api/v1"

PILOT_KEYS = {
    "scope",
    "strategy",
    "architecture",
    "policy",
    "process_design",
    "workload",
    "performance",
    "review_release",
}


def _step(data: dict, key: str) -> dict:
    return next(step for step in data["steps"] if step["key"] == key)


def test_startup_status_shape(client):
    data = client.get(f"{API}/start/status").json()
    assert data["total"] == 9
    assert data["pilot_total"] == 8
    assert len(data["steps"]) == 9
    assert [step["key"] for step in data["steps"]] == [
        "scope",
        "strategy",
        "architecture",
        "policy",
        "process_design",
        "workload",
        "performance",
        "review_release",
        "improvement",
    ]
    assert 0 <= data["readiness_pct"] <= 100
    assert 0 <= data["pilot_readiness_pct"] <= 100
    assert {step["key"] for step in data["steps"] if step["pilot"]} == PILOT_KEYS
    assert _step(data, "improvement")["pilot"] is False
    if data["next_pilot_step"] is not None:
        assert data["next_pilot_step"] in PILOT_KEYS

    for step in data["steps"]:
        assert step["status"] in {"NOT_STARTED", "IN_PROGRESS", "READY", "SKIPPED"}
        assert step["status_label"] in {"还没开始", "进行中", "已具备", "这次先不做（未验证）"}
        assert step["title"] and step["goal"] and step["input"] and step["output"]
        assert step["estimated"]
        assert isinstance(step["evidence"], dict)
        assert step["actions"]
        assert step["evidence_items"], f"{step['key']} 缺少结构化证据"
        for item in step["evidence_items"]:
            assert {"key", "label", "value", "required", "met"} <= set(item)
            assert item["label"]
            assert isinstance(item["required"], bool)
            assert isinstance(item["met"], bool)
        missing = [item for item in step["evidence_items"] if item["required"] and not item["met"]]
        assert (step["status"] == "READY") == (not missing)

    by_key = {step["key"]: step for step in data["steps"]}
    assert by_key["scope"]["status"] == "READY"
    assert by_key["strategy"]["status"] == "READY"
    assert by_key["architecture"]["status"] == "READY"
    assert by_key["workload"]["status"] == "READY"
    assert by_key["performance"]["status"] == "READY"
    # 种子数据还没有 KPI 越线改善项目与已应用变更单
    assert by_key["improvement"]["status"] != "READY"
    assert data["next_step"] is not None


def test_startup_evidence_zero_is_good(client):
    data = client.get(f"{API}/start/status").json()
    raci = _step(data, "architecture")
    invalid = next(item for item in raci["evidence_items"] if item["key"] == "invalid_processes")
    assert invalid["value"] == 0
    assert invalid["met"] is True

    architecture = _step(data, "architecture")
    mapped = next(item for item in architecture["evidence_items"] if item["key"] == "pcf_mapped_l3")
    assert mapped["value"] > 0
    assert mapped["met"] is True


def test_policy_requires_structured_authorization(client):
    """S4 不能只看制度文件：结构化授权规则也是必需证据。"""
    policy = _step(client.get(f"{API}/start/status").json(), "policy")
    items = {item["key"]: item for item in policy["evidence_items"]}
    rules = items["effective_authorization_rules"]
    assert rules["required"] is True
    assert rules["value"] >= 4
    assert rules["met"] is True
    # 种子数据没有生效制度文件，所以 S4 仍不应就绪
    if items["effective_documents"]["value"] == 0:
        assert policy["status"] != "READY"


def test_startup_status_for_owner(owner_client):
    data = owner_client.get(f"{API}/start/status").json()
    assert data["total"] == 9
    assert data["steps"]


def test_skip_marks_unverified_and_unblocks_next(client):
    before = client.get(f"{API}/start/status").json()
    workload = _step(before, "workload")
    assert workload["status"] == "READY"
    ready_before = before["ready_count"]

    try:
        skipped = client.post(f"{API}/start/steps/workload/skip", json={"reason": "样本复核中"})
        assert skipped.status_code == 200, skipped.text
        data = skipped.json()
        step = _step(data, "workload")
        assert step["status"] == "SKIPPED"
        assert step["status_label"] == "这次先不做（未验证）"
        assert step["skipped"] is True
        assert step["skip_reason"] == "样本复核中"
        assert step["skipped_by"] == "系统管理员"
        assert data["ready_count"] == ready_before - 1
        assert data["skipped_count"] == 1
        assert data["next_step"] != "workload"

        # 重复跳过是幂等的：更新原因，不新增记录
        again = client.post(f"{API}/start/steps/workload/skip", json={"reason": "等待新样本"})
        assert again.status_code == 200
        assert again.json()["skipped_count"] == 1
        assert _step(again.json(), "workload")["skip_reason"] == "等待新样本"
    finally:
        undone = client.delete(f"{API}/start/steps/workload/skip")
        assert undone.status_code == 200, undone.text

    restored = undone.json()
    step = _step(restored, "workload")
    assert step["status"] == "READY"
    assert step["skipped"] is False
    assert restored["skipped_count"] == 0
    assert restored["ready_count"] == ready_before


def test_unskip_is_idempotent(client):
    response = client.delete(f"{API}/start/steps/policy/skip")
    assert response.status_code == 200
    assert _step(response.json(), "policy")["skipped"] is False


def test_skip_unknown_step(client):
    assert client.post(f"{API}/start/steps/nope/skip", json={}).status_code == 404
    assert client.delete(f"{API}/start/steps/nope/skip").status_code == 404


def test_skip_requires_manager(owner_client, viewer_client):
    assert owner_client.post(f"{API}/start/steps/policy/skip", json={}).status_code == 403
    assert viewer_client.post(f"{API}/start/steps/policy/skip", json={}).status_code == 403
    assert viewer_client.delete(f"{API}/start/steps/policy/skip").status_code == 403


def _make_pilot_ready():
    """直接落库构造 S4/阶段 8 证据；返回清理函数，避免污染其他用例。"""
    db = SessionLocal()
    process = db.scalar(select(ProcessArch).where(ProcessArch.level == 3).limit(1))
    admin = db.scalar(select(User).where(User.username == "admin"))
    old_published = process.published_model_version
    for document in db.scalars(
        select(ProcessDocument).where(ProcessDocument.code == "DOC-GATE-TEST")
    ).all():
        db.query(ProcessDocumentVersion).filter(
            ProcessDocumentVersion.document_id == document.id
        ).delete()
        db.delete(document)
    for rule in db.scalars(
        select(AuthorizationRule).where(AuthorizationRule.code == "AUTH-GATE-TEST")
    ).all():
        db.delete(rule)
    db.flush()

    document = ProcessDocument(
        code="DOC-GATE-TEST",
        title="门禁测试 SOP",
        process_id=process.id,
        category="SOP",
        is_active=True,
    )
    db.add(document)
    db.flush()
    version = ProcessDocumentVersion(
        document_id=document.id,
        version_label="1.0",
        status=DeliverableStatus.EFFECTIVE.value,
        valid_from=date.today() - timedelta(days=1),
        approved_by="系统管理员",
        approved_by_id=admin.id,
    )
    db.add(version)
    db.flush()
    document.current_version_id = version.id
    db.add(
        AuthorizationRule(
            code="AUTH-GATE-TEST",
            title="门禁测试规则",
            matter="门禁测试事项",
            category="B",
            status=AuthorizationStatus.EFFECTIVE.value,
            approver_label="测试审批人",
            exception_path="测试例外路径",
            evidence_required="测试证据",
            owner_user_id=admin.id,
        )
    )
    process.published_model_version = max(process.published_model_version or 0, 1)
    db.commit()
    process_id = process.id
    db.close()

    def cleanup() -> None:
        session = SessionLocal()
        try:
            for document in session.scalars(
                select(ProcessDocument).where(ProcessDocument.code == "DOC-GATE-TEST")
            ).all():
                session.query(ProcessDocumentVersion).filter(
                    ProcessDocumentVersion.document_id == document.id
                ).delete()
                session.delete(document)
            for rule in session.scalars(
                select(AuthorizationRule).where(AuthorizationRule.code == "AUTH-GATE-TEST")
            ).all():
                session.delete(rule)
            row = session.get(ProcessArch, process_id)
            if row is not None:
                row.published_model_version = old_published
            session.commit()
        finally:
            session.close()

    return cleanup


def test_pilot_confirm_gate(client):
    # 任一试点阶段被跳过或未就绪时，门禁必须拒绝
    client.post(f"{API}/start/steps/policy/skip", json={"reason": "门禁测试"})
    try:
        rejected = client.post(f"{API}/start/pilot/confirm", json={"note": "测试"})
        assert rejected.status_code == 409, rejected.text
        assert "首次上线条件未满足" in rejected.json()["detail"]
    finally:
        client.delete(f"{API}/start/steps/policy/skip")

    cleanup = _make_pilot_ready()
    try:
        status = client.get(f"{API}/start/status").json()
        assert status["pilot_gate_open"] is True, status["pilot_missing_steps"]

        confirmed = client.post(f"{API}/start/pilot/confirm", json={"note": "试运行通过"})
        assert confirmed.status_code == 200, confirmed.text
        data = confirmed.json()
        assert data["pilot_confirmed"] is True
        assert data["pilot_confirmed_by"] == "系统管理员"
        assert data["pilot_confirm_note"] == "试运行通过"
        assert data["pilot_stale"] is False
        assert data["pilot_missing_steps"] == []

        revoked = client.delete(f"{API}/start/pilot/confirm")
        assert revoked.status_code == 200
        assert revoked.json()["pilot_confirmed"] is False
    finally:
        cleanup()
        client.delete(f"{API}/start/pilot/confirm")


def test_pilot_confirm_requires_manager(owner_client, viewer_client):
    assert owner_client.post(f"{API}/start/pilot/confirm", json={}).status_code == 403
    assert viewer_client.post(f"{API}/start/pilot/confirm", json={}).status_code == 403
    assert viewer_client.delete(f"{API}/start/pilot/confirm").status_code == 403
