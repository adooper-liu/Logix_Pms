"""ArchiMate-lite 架构关系与主张级证据的只读契约。"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, update

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models.asset_graph import (
    ActivityRelation,
    EdgeHandoffLink,
    EvidenceAdjudication,
    EvidenceClaim,
    EvidenceClaimTarget,
    NodeActivityLink,
    UnmodeledActivity,
)
from app.models.document_candidate import DocumentCandidateActivity
from app.models.execution import FormDefinition, ProcessRule
from app.models.log_import import (
    LogComparisonReceipt,
    ProcessLogEvent,
    ProcessLogImport,
)
from app.models.maturity import GateAttestation
from app.models.monitor import KpiDefinition, KpiRecord
from app.models.process import ProcessArch, ProcessEdge, ProcessModelVersion, ProcessNode
from app.models.process_document import (
    CompiledAssetComponent,
    ProcessDocument,
    ProcessDocumentVersion,
)
from app.models.project import Project
from app.models.strategy import ObjectiveProcessLink, StrategyObjective
from app.models.tool_sheet import ToolSheet
from app.services import maturity as maturity_service
from app.services import preview as preview_service
from app.services import storage as storage_service

API = "/api/v1"


def _create_process() -> dict:
    suffix = uuid4().hex[:8]
    with SessionLocal() as db:
        process = ProcessArch(
            code=f"L3-T{suffix}",
            name="资产关系测试流程",
            level=3,
            owner="测试",
            is_draft=False,
        )
        db.add(process)
        db.flush()

        a1 = ProcessArch(code=f"L4-T{suffix}-1", name="接收订单", level=4, parent_id=process.id)
        a2 = ProcessArch(code=f"L4-T{suffix}-2", name="价格审批", level=4, parent_id=process.id)
        a3 = ProcessArch(code=f"L4-T{suffix}-3", name="电话确认", level=4, parent_id=process.id)
        db.add_all([a1, a2, a3])
        db.flush()

        version = ProcessModelVersion(
            process_id=process.id,
            version=1,
            status="PUBLISHED",
            snapshot={},
            published_at=utcnow(),
        )
        db.add(version)
        db.flush()
        process.model_version = 1
        process.published_model_version = 1

        nodes = [
            ProcessNode(
                process_id=process.id,
                node_key="n1",
                name="接收订单",
                node_type="TASK",
                lane="销售运营",
                owner_role="销售员",
                sequence_order=1,
                process_arch_id=a1.id,
            ),
            ProcessNode(
                process_id=process.id,
                node_key="n2",
                name="价格审批",
                node_type="APPROVAL",
                lane="财务",
                owner_role="财务经理",
                sequence_order=2,
                process_arch_id=a2.id,
            ),
            ProcessNode(
                process_id=process.id,
                node_key="n3",
                name="是否超授权",
                node_type="DECISION",
                lane="销售运营",
                owner_role="销售员",
                sequence_order=3,
            ),
            ProcessNode(
                process_id=process.id,
                node_key="s",
                name="开始",
                node_type="START",
                lane="销售运营",
                sequence_order=0,
            ),
            ProcessNode(
                process_id=process.id,
                node_key="e",
                name="结束",
                node_type="END",
                lane="销售运营",
                sequence_order=4,
            ),
        ]
        db.add_all(nodes)
        db.flush()
        db.add(ProcessEdge(process_id=process.id, source_key="n1", target_key="n2"))

        db.add_all(
            [
                FormDefinition(
                    process_id=process.id,
                    node_key="n1",
                    name="订单接收单",
                    fields=[],
                    version=1,
                    is_active=True,
                ),
                FormDefinition(
                    process_id=process.id,
                    node_key="n2",
                    name="价格审批单",
                    fields=[],
                    version=1,
                    is_active=True,
                ),
                ProcessRule(
                    process_id=process.id,
                    node_key="n3",
                    name="超授权升级",
                    conditions=[],
                    target_node_key="n2",
                    priority=100,
                    version=1,
                    is_active=True,
                ),
            ]
        )

        db.add_all(
            [
                NodeActivityLink(
                    model_version_id=version.id,
                    process_id=process.id,
                    node_key="n1",
                    activity_id=a1.id,
                    relation="REALIZES",
                    path_condition="STANDARD",
                    coverage=1.0,
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
                NodeActivityLink(
                    model_version_id=version.id,
                    process_id=process.id,
                    node_key="n2",
                    activity_id=a2.id,
                    relation="REALIZES",
                    path_condition="STANDARD",
                    coverage=1.0,
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
                NodeActivityLink(
                    model_version_id=version.id,
                    process_id=process.id,
                    node_key="n2",
                    activity_id=a2.id,
                    relation="CONTROLS",
                    path_condition="STANDARD",
                    coverage=1.0,
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
                ActivityRelation(
                    model_version_id=version.id,
                    process_id=process.id,
                    source_activity_id=a1.id,
                    target_activity_id=process.id,
                    relation="PART_OF",
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
                EdgeHandoffLink(
                    model_version_id=version.id,
                    process_id=process.id,
                    edge_key="n1->n2",
                    from_activity_id=a1.id,
                    to_activity_id=a2.id,
                    handoff_type="HANDOFF",
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
                UnmodeledActivity(
                    model_version_id=version.id,
                    process_id=process.id,
                    activity_id=a3.id,
                    reason="线下电话，模型无对应节点",
                    source_ref="访谈 2026-10-28",
                    confirmed_by_name="测试",
                    confirmed_at=utcnow(),
                ),
            ]
        )

        claim_ok = EvidenceClaim(
            process_id=process.id,
            claim="接收订单由销售员完成",
            claim_type="EXISTENCE",
            source_type="TOOL_SHEET",
            source_id=1,
            method="OBSERVED",
            samples=5,
            status="SUPPORTED",
            created_by_name="测试",
        )
        claim_conflict = EvidenceClaim(
            process_id=process.id,
            claim="价格审批为 2 级",
            claim_type="CONTROL",
            source_type="DOCUMENT_VERSION",
            source_id=2,
            method="DOCUMENTED",
            conflict_group="CG-TEST",
            status="CONFLICTED",
            created_by_name="测试",
        )
        db.add_all([claim_ok, claim_conflict])
        db.flush()
        db.add_all(
            [
                EvidenceClaimTarget(
                    claim_id=claim_ok.id,
                    target_type="ACTIVITY",
                    target_id=a1.id,
                    model_version_id=version.id,
                    condition="STANDARD",
                ),
                EvidenceClaimTarget(
                    claim_id=claim_conflict.id,
                    target_type="ACTIVITY",
                    target_id=a2.id,
                    model_version_id=version.id,
                    condition="STANDARD",
                ),
            ]
        )
        db.commit()
        return {
            "process_id": process.id,
            "version_id": version.id,
            "a1_id": a1.id,
            "a2_id": a2.id,
            "a3_id": a3.id,
            "a3_code": a3.code,
        }


def _cleanup_process(pid: int) -> None:
    with SessionLocal() as db:
        groups = list(
            db.scalars(
                select(EvidenceClaim.conflict_group).where(
                    EvidenceClaim.process_id == pid,
                    EvidenceClaim.conflict_group.is_not(None),
                )
            )
        )
        if groups:
            db.execute(
                delete(EvidenceAdjudication).where(EvidenceAdjudication.conflict_group.in_(groups))
            )
        import_ids = list(
            db.scalars(select(ProcessLogImport.id).where(ProcessLogImport.process_id == pid))
        )
        db.execute(delete(LogComparisonReceipt).where(LogComparisonReceipt.process_id == pid))
        if import_ids:
            db.execute(delete(ProcessLogEvent).where(ProcessLogEvent.import_id.in_(import_ids)))
            db.execute(delete(ProcessLogImport).where(ProcessLogImport.id.in_(import_ids)))
        claim_ids = list(
            db.scalars(select(EvidenceClaim.id).where(EvidenceClaim.process_id == pid))
        )
        if claim_ids:
            db.execute(
                delete(EvidenceClaimTarget).where(EvidenceClaimTarget.claim_id.in_(claim_ids))
            )
        db.execute(delete(EvidenceClaim).where(EvidenceClaim.process_id == pid))
        for model in (UnmodeledActivity, EdgeHandoffLink, ActivityRelation, NodeActivityLink):
            db.execute(delete(model).where(model.process_id == pid))
        document_ids = list(
            db.scalars(select(ProcessDocument.id).where(ProcessDocument.process_id == pid))
        )
        version_ids = (
            list(
                db.scalars(
                    select(ProcessDocumentVersion.id).where(
                        ProcessDocumentVersion.document_id.in_(document_ids)
                    )
                )
            )
            if document_ids
            else []
        )
        storage_keys = (
            list(
                db.scalars(
                    select(ProcessDocumentVersion.storage_key).where(
                        ProcessDocumentVersion.id.in_(version_ids),
                        ProcessDocumentVersion.storage_key.is_not(None),
                    )
                )
            )
            if version_ids
            else []
        )
        db.execute(
            delete(DocumentCandidateActivity).where(DocumentCandidateActivity.process_id == pid)
        )
        if version_ids:
            db.execute(
                delete(CompiledAssetComponent).where(
                    CompiledAssetComponent.document_version_id.in_(version_ids)
                )
            )
            db.execute(
                delete(ProcessDocumentVersion).where(ProcessDocumentVersion.id.in_(version_ids))
            )
        if document_ids:
            db.execute(delete(ProcessDocument).where(ProcessDocument.id.in_(document_ids)))
        storage = storage_service.get_storage()
        for key in storage_keys:
            try:
                storage.delete(key)
            except Exception:  # noqa: BLE001 - 测试清理不因文件缺失失败
                pass
        db.execute(delete(ToolSheet).where(ToolSheet.process_id == pid))
        db.execute(delete(ProcessRule).where(ProcessRule.process_id == pid))
        db.execute(delete(FormDefinition).where(FormDefinition.process_id == pid))
        db.execute(delete(ProcessNode).where(ProcessNode.process_id == pid))
        db.execute(delete(ProcessModelVersion).where(ProcessModelVersion.process_id == pid))
        db.execute(delete(ProcessArch).where(ProcessArch.parent_id == pid))
        db.execute(delete(ProcessArch).where(ProcessArch.id == pid))
        db.commit()


@pytest.fixture
def asset_process():
    """测试数据用完即删，避免新增 L3 污染基准覆盖率等全局计数。"""
    ids = _create_process()
    yield ids
    _cleanup_process(ids["process_id"])


@pytest.fixture
def blank_process():
    """只有模型/节点/表单/规则，没有关系与证据，用于验证写入。"""
    ids = _create_process()
    pid = ids["process_id"]
    with SessionLocal() as db:
        claim_ids = list(
            db.scalars(select(EvidenceClaim.id).where(EvidenceClaim.process_id == pid))
        )
        if claim_ids:
            db.execute(
                delete(EvidenceClaimTarget).where(EvidenceClaimTarget.claim_id.in_(claim_ids))
            )
        db.execute(delete(EvidenceClaim).where(EvidenceClaim.process_id == pid))
        for model in (UnmodeledActivity, EdgeHandoffLink, ActivityRelation, NodeActivityLink):
            db.execute(delete(model).where(model.process_id == pid))
        db.execute(
            update(ProcessNode).where(ProcessNode.process_id == pid).values(process_arch_id=None)
        )
        db.commit()
    yield ids
    _cleanup_process(pid)


def test_architecture_map_and_readiness(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]

    mapped = client.get(f"{API}/processes/{pid}/architecture-map")
    assert mapped.status_code == 200, mapped.text
    data = mapped.json()
    assert data["versioned"] is True
    assert data["model_version_id"] == ids["version_id"]
    assert len(data["nodes"]) == 5
    assert len(data["links"]) == 3
    assert len(data["activity_relations"]) == 1
    assert len(data["handoffs"]) == 1
    assert len(data["unmodeled"]) == 1

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness")
    assert readiness.status_code == 200, readiness.text
    result = readiness.json()
    assert result["metrics"]["activity_nodes"] == 2
    assert result["metrics"]["mapped_activities"] == 2
    assert result["metrics"]["owner_ready"] == 2
    assert result["metrics"]["carrier_ready"] == 2
    assert result["metrics"]["decision_nodes"] == 1
    assert result["metrics"]["rule_ready"] == 1
    assert result["metrics"]["control_links"] == 1
    assert result["metrics"]["claims_conflicted"] == 1
    assert result["can_generate_draft"] is True
    assert result["can_submit_review"] is False
    assert any(item["code"] == "EVIDENCE_CONFLICT" for item in result["blockers"])

    claims = client.get(f"{API}/processes/{pid}/evidence-claims")
    assert claims.status_code == 200, claims.text
    payload = claims.json()
    assert len(payload["claims"]) == 2
    assert "CG-TEST" in payload["conflicts"]
    assert any(ids["a3_code"] in item for item in payload["unknown_targets"])
    assert payload["labels"]["status"]["CONFLICTED"] == "冲突"


def test_adjudication_unblocks_submission(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    with SessionLocal() as db:
        db.add(
            EvidenceAdjudication(
                conflict_group="CG-TEST",
                decision="DOCUMENT",
                rationale="以现行制度为准",
                decided_by_name="流程管理科",
            )
        )
        db.commit()

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert readiness["can_submit_review"] is True
    assert readiness["metrics"]["claims_conflicted"] == 1
    assert not any(item["code"] == "EVIDENCE_CONFLICT" for item in readiness["blockers"])


def test_expired_claim_blocks_review(client, asset_process):
    pid = asset_process["process_id"]
    with SessionLocal() as db:
        db.add(
            EvidenceClaim(
                process_id=pid,
                claim="过期观测",
                claim_type="TIME",
                source_type="TOOL_SHEET",
                source_id=3,
                method="OBSERVED",
                status="SUPPORTED",
                valid_to=date(2020, 1, 1),
                created_by_name="测试",
            )
        )
        db.commit()

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert readiness["metrics"]["claims_expired"] == 1
    assert any(item["code"] == "EVIDENCE_EXPIRED" for item in readiness["blockers"])
    assert readiness["can_submit_review"] is False


def test_asset_readiness_rejects_unknown_and_non_l3(client, anon_client, asset_process):
    assert client.get(f"{API}/processes/99999999/asset-readiness").status_code == 404
    l1 = client.get(f"{API}/process-map/flat?level=1").json()[0]
    assert client.get(f"{API}/processes/{l1['id']}/asset-readiness").status_code == 400
    l4 = client.get(f"{API}/process-map/flat?level=4").json()[0]
    assert client.get(f"{API}/processes/{l4['id']}/asset-readiness").status_code == 400

    assert (
        anon_client.get(
            f"{API}/processes/{asset_process['process_id']}/asset-readiness"
        ).status_code
        == 401
    )


def test_write_architecture_relations(client, blank_process, viewer_client):
    ids = blank_process
    pid = ids["process_id"]
    a1, a2, a3 = ids["a1_id"], ids["a2_id"], ids["a3_id"]

    first = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={
            "node_key": "n1",
            "activity_id": a1,
            "relation": "REALIZES",
            "path_condition": "STANDARD",
            "coverage": 1.0,
        },
    )
    assert first.status_code == 200, first.text
    link_id = first.json()["id"]

    again = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={
            "node_key": "n1",
            "activity_id": a1,
            "relation": "REALIZES",
            "path_condition": "STANDARD",
            "coverage": 0.8,
        },
    )
    assert again.status_code == 200, again.text
    assert again.json()["id"] == link_id
    assert again.json()["coverage"] == 0.8

    assert (
        client.post(
            f"{API}/processes/{pid}/architecture-map/links",
            json={"node_key": "n2", "activity_id": a2, "relation": "REALIZES"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"{API}/processes/{pid}/architecture-map/links",
            json={"node_key": "n2", "activity_id": a2, "relation": "CONTROLS"},
        ).status_code
        == 200
    )

    relation = client.post(
        f"{API}/processes/{pid}/architecture-map/relations",
        json={
            "source_activity_id": a1,
            "target_activity_id": a2,
            "relation": "DECOMPOSES",
        },
    )
    assert relation.status_code == 200, relation.text

    handoff = client.post(
        f"{API}/processes/{pid}/architecture-map/handoffs",
        json={
            "edge_key": "n1→n2",
            "from_activity_id": a1,
            "to_activity_id": a2,
            "handoff_type": "HANDOFF",
        },
    )
    assert handoff.status_code == 200, handoff.text
    assert handoff.json()["edge_key"] == "n1->n2"

    unmodeled = client.post(
        f"{API}/processes/{pid}/architecture-map/unmodeled",
        json={"activity_id": a3, "reason": "线下电话，模型无对应节点"},
    )
    assert unmodeled.status_code == 200, unmodeled.text

    data = client.get(f"{API}/processes/{pid}/architecture-map").json()
    assert len(data["links"]) == 3
    assert len(data["activity_relations"]) == 1
    assert len(data["handoffs"]) == 1
    assert len(data["unmodeled"]) == 1

    invalid_activity = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={"node_key": "n1", "activity_id": pid},
    )
    assert invalid_activity.status_code == 400

    missing_node = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={"node_key": "nope", "activity_id": a1},
    )
    assert missing_node.status_code == 404

    start_link = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={"node_key": "s", "activity_id": a1, "relation": "REALIZES"},
    )
    assert start_link.status_code == 400

    assert (
        viewer_client.post(
            f"{API}/processes/{pid}/architecture-map/links",
            json={"node_key": "n1", "activity_id": a1},
        ).status_code
        == 403
    )

    # 未发布模型版本时拒绝写入
    with SessionLocal() as db:
        db.execute(delete(ProcessModelVersion).where(ProcessModelVersion.process_id == pid))
        db.commit()
    no_version = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={"node_key": "n1", "activity_id": a1},
    )
    assert no_version.status_code == 409


def test_write_evidence_claim_and_adjudicate(client, blank_process, viewer_client):
    ids = blank_process
    pid = ids["process_id"]
    a1, a2 = ids["a1_id"], ids["a2_id"]
    with SessionLocal() as db:
        sheet = ToolSheet(
            tool_code="VSM",
            process_id=pid,
            title="测试观测",
            fields=[{"key": "steps", "value": "n1 10 分钟"}],
            revision=0,
            created_by="测试",
        )
        db.add(sheet)
        db.commit()
        sheet_id = sheet.id

    payload = {
        "claim": "A1 由销售员完成，A2 等待约 120 分钟",
        "claim_type": "TIME",
        "source_type": "TOOL_SHEET",
        "source_id": sheet_id,
        "method": "OBSERVED",
        "samples": 12,
        "status": "CONFLICTED",
        "conflict_group": "CG-WRITE",
        "targets": [
            {"target_type": "ACTIVITY", "target_id": a1, "condition": "STANDARD"},
            {
                "target_type": "TIME_FIELD",
                "target_id": a2,
                "field": "wait",
                "condition": "STANDARD",
            },
        ],
    }
    created = client.post(f"{API}/processes/{pid}/evidence-claims", json=payload)
    assert created.status_code == 200, created.text
    claim = created.json()
    assert claim["source_hash"]
    assert claim["source_version"].startswith("revision:")
    assert len(claim["targets"]) == 2
    claim_id = claim["id"]

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    assert "CG-WRITE" in claims["conflicts"]

    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{claim_id}/adjudicate",
        json={"decision": "ACCEPT_OBSERVED", "rationale": "以 12 单现场观测为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text
    assert adjudicated.json()["decision"] == "ACCEPT_OBSERVED"

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    assert "CG-WRITE" not in claims["conflicts"]
    row = next(item for item in claims["claims"] if item["id"] == claim_id)
    assert len(row["adjudications"]) == 1

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert not any(item["code"] == "EVIDENCE_CONFLICT" for item in readiness["blockers"])

    invalid_target = client.post(
        f"{API}/processes/{pid}/evidence-claims",
        json={**payload, "targets": [{"target_type": "ACTIVITY", "target_id": pid}]},
    )
    assert invalid_target.status_code == 400

    assert (
        viewer_client.post(f"{API}/processes/{pid}/evidence-claims", json=payload).status_code
        == 403
    )


def test_asset_package_preview_commit_and_transition(client, asset_process, viewer_client):
    ids = asset_process
    pid = ids["process_id"]

    preview = client.post(f"{API}/processes/{pid}/asset-packages/compile")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["can_generate"] is True
    assert data["model_version_id"] == ids["version_id"]
    assert ids["process_id"] == data["process_id"]
    assert data["content_hash"] == data["manifest"]["content_hash"]
    assert any(item["code"] == "EVIDENCE_CONFLICT" for item in data["blockers"])
    assert "作业标准" in data["preview_html"]
    assert "流程级 RACI" in data["preview_html"]
    assert ids["a3_code"] in data["preview_html"]

    assert viewer_client.post(f"{API}/processes/{pid}/asset-packages").status_code == 403

    created = client.post(f"{API}/processes/{pid}/asset-packages")
    assert created.status_code == 200, created.text
    package = created.json()
    assert package["version_label"] == "1.0"
    assert package["status"] == "DRAFT"
    assert package["document_code"].startswith("AP-")
    assert package["manifest"]["rule_version"] == "asset-compile-v1"
    version_id = package["version_id"]

    fetched = client.get(f"{API}/asset-packages/{version_id}")
    assert fetched.status_code == 200, fetched.text
    assert "作业标准" in fetched.json()["preview_html"]

    blocked = client.post(
        f"{API}/asset-packages/{version_id}/transition",
        json={"status": "IN_REVIEW"},
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["message"]

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    claim = next(item for item in claims["claims"] if item["conflict_group"] == "CG-TEST")
    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{claim['id']}/adjudicate",
        json={"decision": "ACCEPT_DOCUMENT", "rationale": "以现行制度为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text

    moved = client.post(
        f"{API}/asset-packages/{version_id}/transition",
        json={"status": "IN_REVIEW"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "IN_REVIEW"


def test_legacy_pointer_counts_as_mapped(client, asset_process):
    pid = asset_process["process_id"]
    with SessionLocal() as db:
        db.execute(delete(NodeActivityLink).where(NodeActivityLink.process_id == pid))
        db.commit()

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert readiness["metrics"]["mapped_activities"] == 2
    assert not any(item["code"] == "NODE_ACTIVITY_UNMAPPED" for item in readiness["blockers"])
    assert any("兼容主活动指针" in item for item in readiness["warnings"])

    mapping = client.get(f"{API}/processes/{pid}/architecture-map").json()
    legacy = [row for row in mapping["links"] if row.get("legacy")]
    assert len(legacy) == 2
    assert all(row["relation"] == "REALIZES" for row in legacy)


def test_asset_package_blocks_unmapped_nodes(client, blank_process):
    pid = blank_process["process_id"]
    preview = client.post(f"{API}/processes/{pid}/asset-packages/compile")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["can_generate"] is False
    assert any(item["code"] == "NODE_ACTIVITY_UNMAPPED" for item in data["blockers"])
    assert "拒绝生成" in data["preview_html"]

    commit = client.post(f"{API}/processes/{pid}/asset-packages")
    assert commit.status_code == 409


def test_asset_package_requires_published_model(client, blank_process):
    pid = blank_process["process_id"]
    with SessionLocal() as db:
        db.execute(delete(ProcessModelVersion).where(ProcessModelVersion.process_id == pid))
        db.commit()

    preview = client.post(f"{API}/processes/{pid}/asset-packages/compile")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert data["can_generate"] is False
    assert any(item["code"] == "MODEL_NOT_VERSIONED" for item in data["blockers"])

    assert client.post(f"{API}/processes/{pid}/asset-packages").status_code == 409


def _commit_package(client, pid: int) -> dict:
    created = client.post(f"{API}/processes/{pid}/asset-packages")
    assert created.status_code == 200, created.text
    return created.json()


def test_asset_package_pdf_requires_converter(client, asset_process, monkeypatch):
    package = _commit_package(client, asset_process["process_id"])
    monkeypatch.setattr(preview_service, "converter_available", lambda: False)
    response = client.get(f"{API}/asset-packages/{package['version_id']}/pdf")
    assert response.status_code == 503
    assert "LibreOffice" in response.json()["detail"]


def test_asset_package_pdf(client, asset_process, monkeypatch):
    package = _commit_package(client, asset_process["process_id"])
    monkeypatch.setattr(preview_service, "converter_available", lambda: True)
    monkeypatch.setattr(
        preview_service, "convert_to_pdf", lambda source, filename: b"%PDF-1.4 test"
    )
    response = client.get(f"{API}/asset-packages/{package['version_id']}/pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_delete_architecture_relations(client, blank_process, viewer_client):
    ids = blank_process
    pid = ids["process_id"]
    a1, a2, a3 = ids["a1_id"], ids["a2_id"], ids["a3_id"]

    link = client.post(
        f"{API}/processes/{pid}/architecture-map/links",
        json={"node_key": "n1", "activity_id": a1, "relation": "REALIZES"},
    ).json()
    relation = client.post(
        f"{API}/processes/{pid}/architecture-map/relations",
        json={
            "source_activity_id": a1,
            "target_activity_id": a2,
            "relation": "DECOMPOSES",
        },
    ).json()
    handoff = client.post(
        f"{API}/processes/{pid}/architecture-map/handoffs",
        json={"edge_key": "n1->n2", "handoff_type": "HANDOFF"},
    ).json()
    unmodeled = client.post(
        f"{API}/processes/{pid}/architecture-map/unmodeled",
        json={"activity_id": a3, "reason": "线下电话"},
    ).json()

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert readiness["metrics"]["mapped_activities"] == 1

    deleted = client.delete(f"{API}/processes/{pid}/architecture-map/links/{link['id']}")
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["deleted"] == link["id"]

    readiness = client.get(f"{API}/processes/{pid}/asset-readiness").json()
    assert readiness["metrics"]["mapped_activities"] == 0
    assert any(item["code"] == "NODE_ACTIVITY_UNMAPPED" for item in readiness["blockers"])

    for path, row in (
        ("relations", relation),
        ("handoffs", handoff),
        ("unmodeled", unmodeled),
    ):
        response = client.delete(f"{API}/processes/{pid}/architecture-map/{path}/{row['id']}")
        assert response.status_code == 200, response.text

    mapping = client.get(f"{API}/processes/{pid}/architecture-map").json()
    assert not mapping["links"]
    assert not mapping["activity_relations"]
    assert not mapping["handoffs"]
    assert not mapping["unmodeled"]

    again = client.delete(f"{API}/processes/{pid}/architecture-map/links/{link['id']}")
    assert again.status_code == 404

    assert (
        viewer_client.delete(
            f"{API}/processes/{pid}/architecture-map/relations/{relation['id']}"
        ).status_code
        == 403
    )


def test_component_impact(client, asset_process):
    pid = asset_process["process_id"]
    package = _commit_package(client, pid)
    a1 = asset_process["a1_id"]

    by_activity = client.get(f"{API}/asset-packages/impact?activity_id={a1}")
    assert by_activity.status_code == 200, by_activity.text
    payload = by_activity.json()
    assert payload["total"] >= 1
    assert all(item["version_id"] == package["version_id"] for item in payload["items"])
    assert any(item["component_type"] in {"SOP_SECTION", "FORM_REF"} for item in payload["items"])

    with SessionLocal() as db:
        row = db.scalar(
            select(CompiledAssetComponent).where(
                CompiledAssetComponent.document_version_id == package["version_id"],
                CompiledAssetComponent.component_type == "FORM_REF",
            )
        )
        assert row is not None
        form_ref = row.component_ref_id

    by_form = client.get(
        f"{API}/asset-packages/impact?component_type=FORM_REF&component_ref_id={form_ref}"
    )
    assert by_form.status_code == 200, by_form.text
    assert any(item["component_type"] == "FORM_REF" for item in by_form.json()["items"])

    assert client.get(f"{API}/asset-packages/impact").status_code == 400
    assert (
        client.get(
            f"{API}/asset-packages/impact?component_type=NOPE&component_ref_id=1"
        ).status_code
        == 400
    )


def test_asset_print_pack(client, asset_process, monkeypatch):
    pid = asset_process["process_id"]
    first = _commit_package(client, pid)
    second = _commit_package(client, pid)
    assert second["version_id"] != first["version_id"]

    html = client.get(f"{API}/processes/{pid}/asset-packages/print-pack?format=html")
    assert html.status_code == 200, html.text
    text = html.text
    assert "流程资产打印包" in text
    assert "资产关系测试流程" in text
    assert first["version_label"] in text
    assert second["version_label"] in text

    filtered = client.get(
        f"{API}/processes/{pid}/asset-packages/print-pack"
        f"?format=html&version_ids={second['version_id']}"
    )
    assert filtered.status_code == 200, filtered.text
    assert second["version_label"] in filtered.text
    assert first["version_label"] not in filtered.text

    monkeypatch.setattr(preview_service, "converter_available", lambda: False)
    assert (
        client.get(f"{API}/processes/{pid}/asset-packages/print-pack?format=pdf").status_code == 503
    )
    monkeypatch.setattr(preview_service, "converter_available", lambda: True)
    monkeypatch.setattr(
        preview_service, "convert_to_pdf", lambda source, filename: b"%PDF-1.4 pack"
    )
    pdf = client.get(f"{API}/processes/{pid}/asset-packages/print-pack?format=pdf")
    assert pdf.status_code == 200, pdf.text
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")

    assert (
        client.get(
            f"{API}/processes/{pid}/asset-packages/print-pack?format=html&version_ids=abc"
        ).status_code
        == 400
    )


def test_asset_print_pack_needs_package(client, blank_process):
    pid = blank_process["process_id"]
    response = client.get(f"{API}/processes/{pid}/asset-packages/print-pack?format=html")
    assert response.status_code == 404


def test_diagnosis_readiness_and_commit(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]

    before = client.get(f"{API}/processes/{pid}/diagnosis-readiness")
    assert before.status_code == 200, before.text
    data = before.json()
    assert data["can_compile"] is True
    assert data["source_profile"]["observed_time_claims"] == 0
    quantitative = next(item for item in data["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is False
    assert any(item["code"] == "OBSERVED_TIME_MISSING" for item in data["blockers"])
    assert any(item["code"] == "EVIDENCE_CONFLICT" for item in data["blockers"])

    with SessionLocal() as db:
        sheet = ToolSheet(
            tool_code="VSM",
            process_id=pid,
            title="诊断观测",
            fields=[],
            revision=0,
            created_by="测试",
        )
        db.add(sheet)
        db.commit()
        sheet_id = sheet.id

    observed = client.post(
        f"{API}/processes/{pid}/evidence-claims",
        json={
            "claim": "A1 平均等待 120 分钟",
            "claim_type": "TIME",
            "source_type": "TOOL_SHEET",
            "source_id": sheet_id,
            "method": "OBSERVED",
            "samples": 12,
            "targets": [
                {
                    "target_type": "TIME_FIELD",
                    "target_id": ids["a1_id"],
                    "field": "wait",
                    "condition": "STANDARD",
                }
            ],
        },
    )
    assert observed.status_code == 200, observed.text

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    conflict = next(item for item in claims["claims"] if item["conflict_group"] == "CG-TEST")
    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{conflict['id']}/adjudicate",
        json={"decision": "ACCEPT_DOCUMENT", "rationale": "以现行制度为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text

    after = client.get(f"{API}/processes/{pid}/diagnosis-readiness").json()
    assert after["source_profile"]["observed_time_claims"] == 1
    quantitative = next(item for item in after["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is True
    assert not any(item["code"] == "EVIDENCE_CONFLICT" for item in after["blockers"])

    preview = client.post(f"{API}/processes/{pid}/diagnosis-packet/compile")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["can_compile"] is True
    assert body["manifest"]["kind"] == "DIAGNOSIS"
    assert "诊断证据包" in body["preview_html"]
    assert "模型估算" in body["preview_html"]
    assert "PCE" in body["preview_html"]

    created = client.post(f"{API}/processes/{pid}/diagnosis-packet")
    assert created.status_code == 200, created.text
    package = created.json()
    assert package["kind"] == "DIAGNOSIS"
    assert package["document_code"].startswith("DG-")
    assert package["version_label"] == "1.0"
    assert package["status"] == "DRAFT"

    fetched = client.get(f"{API}/asset-packages/{package['version_id']}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["kind"] == "DIAGNOSIS"


def test_diagnosis_hard_blocker(client, blank_process):
    pid = blank_process["process_id"]
    readiness = client.get(f"{API}/processes/{pid}/diagnosis-readiness")
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["can_compile"] is False
    assert any(item["code"] == "NODE_ACTIVITY_UNMAPPED" for item in readiness.json()["blockers"])
    commit = client.post(f"{API}/processes/{pid}/diagnosis-packet")
    assert commit.status_code == 409


def test_model_source_profile_and_registration(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    a1, a2 = ids["a1_id"], ids["a2_id"]

    profile = client.get(f"{API}/processes/{pid}/model-source-profile")
    assert profile.status_code == 200, profile.text
    data = profile.json()
    assert data["activity_count"] == 2
    assert data["covered_activities"] == 2
    assert data["methods"].get("OBSERVED") == 1
    assert data["methods"].get("DOCUMENTED") == 1
    assert data["source_types"].get("TOOL_SHEET") == 1
    assert data["gaps"] == []
    assert data["observed_time_claims"] == 0
    quantitative = next(item for item in data["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is False

    with SessionLocal() as db:
        sheet = ToolSheet(
            tool_code="VSM",
            process_id=pid,
            title="As-Is 来源",
            fields=[],
            revision=0,
            created_by="测试",
        )
        db.add(sheet)
        db.commit()
        sheet_id = sheet.id

    created = client.post(
        f"{API}/processes/{pid}/evidence-claims",
        json={
            "claim": "制度与现场观测覆盖接收与审批",
            "claim_type": "TIME",
            "source_type": "TOOL_SHEET",
            "source_id": sheet_id,
            "method": "OBSERVED",
            "samples": 5,
            "targets": [
                {"target_type": "ACTIVITY", "target_id": a1, "condition": "ALL"},
                {"target_type": "ACTIVITY", "target_id": a2, "condition": "ALL"},
                {
                    "target_type": "TIME_FIELD",
                    "target_id": a1,
                    "field": "wait",
                    "condition": "ALL",
                },
            ],
        },
    )
    assert created.status_code == 200, created.text

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    row = next(item for item in claims["claims"] if item["id"] == created.json()["id"])
    assert all(target["model_version_id"] == ids["version_id"] for target in row["targets"])

    after = client.get(f"{API}/processes/{pid}/model-source-profile").json()
    assert after["observed_time_claims"] == 1
    quantitative = next(item for item in after["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is False

    conflict = next(item for item in claims["claims"] if item["conflict_group"] == "CG-TEST")
    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{conflict['id']}/adjudicate",
        json={"decision": "ACCEPT_DOCUMENT", "rationale": "以现行制度为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text

    final = client.get(f"{API}/processes/{pid}/model-source-profile").json()
    quantitative = next(item for item in final["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is True
    assert final["observed_time_claims"] == 1


def _create_document_version(pid: int, text: str) -> tuple[int, int]:
    suffix = uuid4().hex[:8]
    storage = storage_service.get_storage()
    key = storage_service.build_key(f"test-docs/{pid}", f"sop-{suffix}.txt")
    digest, size = storage.save(key, io.BytesIO(text.encode("utf-8")), storage_service.max_bytes())
    with SessionLocal() as db:
        document = ProcessDocument(
            process_id=pid,
            code=f"PD-T-{suffix}",
            title="订单处理 SOP",
            category="SOP",
            description="测试文档",
            level="PROCESS",
            language="zh-CN",
        )
        db.add(document)
        db.flush()
        version = ProcessDocumentVersion(
            document_id=document.id,
            version_label="1.0",
            status="EFFECTIVE",
            note="测试",
            file_name="sop.txt",
            mime_type="text/plain",
            size_bytes=size,
            checksum=digest,
            storage_backend="local",
            storage_key=key,
            created_by="测试",
        )
        db.add(version)
        db.flush()
        document.current_version_id = version.id
        db.commit()
        return document.id, version.id


def test_document_candidates_extract_confirm_reject(client, asset_process, viewer_client):
    pid = asset_process["process_id"]
    document_id, version_id = _create_document_version(
        pid, "1. 接收订单\n2. 信用检查\n3. 技术评审\n"
    )

    extracted = client.post(
        f"{API}/processes/{pid}/document-candidates/extract",
        json={"document_version_id": version_id},
    )
    assert extracted.status_code == 200, extracted.text
    items = extracted.json()
    assert len(items) == 3
    assert {item["line_no"] for item in items} == {1, 2, 3}
    assert all(item["status"] == "PROPOSED" for item in items)
    assert all(item["confidence"] == "NUMBERED" for item in items)

    again = client.post(
        f"{API}/processes/{pid}/document-candidates/extract",
        json={"document_version_id": version_id},
    )
    assert again.status_code == 200
    assert len(again.json()) == 3

    first, second, third = items
    confirmed = client.post(
        f"{API}/processes/{pid}/document-candidates/{first['id']}/confirm",
        json={},
    )
    assert confirmed.status_code == 200, confirmed.text
    confirmed_data = confirmed.json()
    assert confirmed_data["status"] == "CONFIRMED"
    assert confirmed_data["activity_id"]
    assert confirmed_data["activity_code"].startswith("L4C")

    with SessionLocal() as db:
        activity = db.get(ProcessArch, confirmed_data["activity_id"])
        assert activity is not None
        assert activity.level == 4
        assert activity.parent_id == pid
        assert activity.name == "接收订单"

    rejected = client.post(f"{API}/processes/{pid}/document-candidates/{second['id']}/reject")
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REJECTED"
    assert (
        client.post(
            f"{API}/processes/{pid}/document-candidates/{second['id']}/confirm",
            json={},
        ).status_code
        == 400
    )

    forced = client.post(
        f"{API}/processes/{pid}/document-candidates/extract",
        json={"document_version_id": version_id, "force": True},
    )
    assert forced.status_code == 200, forced.text
    by_line = {item["line_no"]: item for item in forced.json()}
    assert by_line[1]["status"] == "CONFIRMED"
    assert by_line[2]["status"] == "REJECTED"
    assert by_line[3]["status"] == "PROPOSED"

    assert (
        viewer_client.post(
            f"{API}/processes/{pid}/document-candidates/extract",
            json={"document_version_id": version_id},
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"{API}/processes/{pid}/document-candidates/extract",
            json={"document_version_id": 99999999},
        ).status_code
        == 404
    )


def test_log_import_map_commit_and_diagnosis(client, asset_process, viewer_client):
    ids = asset_process
    pid = ids["process_id"]
    csv_text = (
        "case_id,activity,timestamp,resource\n"
        "C1,接收订单,2026-10-01T09:00:00,张三\n"
        "C1,信用检查,2026-10-01T10:00:00,李四\n"
        "C2,接收订单,2026-10-02T09:00:00,张三\n"
        "C2,信用检查,2026-10-02T11:00:00,李四\n"
    )
    upload = client.post(
        f"{API}/processes/{pid}/log-imports",
        files={"file": ("log.csv", csv_text, "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    data = upload.json()
    assert data["row_count"] == 4
    assert data["case_count"] == 2
    assert data["status"] == "DRAFT"
    assert len(data["labels"]) == 2
    import_id = data["id"]
    label_map = {row["label"]: row for row in data["labels"]}
    assert label_map["接收订单"]["suggested_activity_id"] == ids["a1_id"]
    assert label_map["接收订单"]["suggestion_reason"] == "名称/编码匹配"

    assert client.post(f"{API}/processes/{pid}/log-imports/{import_id}/commit").status_code == 400

    mapped = client.post(
        f"{API}/processes/{pid}/log-imports/{import_id}/map",
        json={"mapping": {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}},
    )
    assert mapped.status_code == 200, mapped.text
    metrics = mapped.json()["metrics"]
    assert mapped.json()["status"] == "MAPPED"
    assert metrics["case_count"] == 2
    assert metrics["mapped_events"] == 4
    assert round(metrics["lead_time_minutes"]["mean"]) == 90

    committed = client.post(f"{API}/processes/{pid}/log-imports/{import_id}/commit")
    assert committed.status_code == 200, committed.text
    assert committed.json()["status"] == "COMMITTED"
    assert committed.json()["claim_id"]

    second = client.post(
        f"{API}/processes/{pid}/log-imports",
        files={"file": ("log2.csv", csv_text, "text/csv")},
    )
    assert second.status_code == 200, second.text
    second_labels = {row["label"]: row for row in second.json()["labels"]}
    assert second_labels["信用检查"]["suggested_activity_id"] == ids["a2_id"]
    assert "历史" in second_labels["信用检查"]["suggestion_reason"]

    profile = client.get(f"{API}/processes/{pid}/model-source-profile").json()
    assert profile["observed_time_claims"] >= 1
    assert profile["source_types"].get("LOG_IMPORT") == 1

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    conflict = next(item for item in claims["claims"] if item["conflict_group"] == "CG-TEST")
    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{conflict['id']}/adjudicate",
        json={"decision": "ACCEPT_DOCUMENT", "rationale": "以现行制度为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text

    diagnosis = client.get(f"{API}/processes/{pid}/diagnosis-readiness").json()
    quantitative = next(item for item in diagnosis["uses"] if item["key"] == "quantitative")
    assert quantitative["ready"] is True

    assert (
        viewer_client.post(
            f"{API}/processes/{pid}/log-imports",
            files={"file": ("log.csv", csv_text, "text/csv")},
        ).status_code
        == 403
    )
    bad = client.post(
        f"{API}/processes/{pid}/log-imports",
        files={"file": ("bad.csv", "case_id,activity\nC1,A\n", "text/csv")},
    )
    assert bad.status_code == 400


def test_r1_requires_2_1_to_2_3_and_compiles(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]

    r1 = client.get(f"{API}/processes/{pid}/r1-readiness")
    assert r1.status_code == 200, r1.text
    data = r1.json()
    assert data["can_compile_draft"] is True
    assert data["can_submit_review"] is False
    assert "SIPOC 范围与边界" in data["missing_inputs"]
    assert "VSM 与观测时间" in data["missing_inputs"]
    assert "5Why / 帕累托根因" in data["missing_inputs"]

    preview = client.post(f"{API}/processes/{pid}/r1/compile")
    assert preview.status_code == 200, preview.text
    preview_data = preview.json()
    assert preview_data["can_submit_review"] is False
    assert preview_data["manifest"]["kind"] == "DIAGNOSIS_R1"
    assert preview_data["inputs"]

    created = client.post(f"{API}/processes/{pid}/r1")
    assert created.status_code == 200, created.text
    package = created.json()
    assert package["kind"] == "DIAGNOSIS_R1"
    assert package["document_code"].startswith("DG-")
    assert package["status"] == "DRAFT"

    blocked = client.post(
        f"{API}/asset-packages/{package['version_id']}/transition",
        json={"status": "IN_REVIEW"},
    )
    assert blocked.status_code == 409

    with SessionLocal() as db:
        sipoc = ToolSheet(
            tool_code="SIPOC",
            process_id=pid,
            title="SIPOC",
            fields=[],
            revision=0,
            created_by="测试",
        )
        vsm = ToolSheet(
            tool_code="VSM",
            process_id=pid,
            title="VSM",
            fields=[],
            revision=0,
            created_by="测试",
        )
        why = ToolSheet(
            tool_code="FIVE-WHY",
            process_id=pid,
            title="5Why",
            fields=[],
            revision=0,
            created_by="测试",
        )
        db.add_all([sipoc, vsm, why])
        db.commit()
        sheet_ids = {"SIPOC": sipoc.id, "VSM": vsm.id, "FIVE-WHY": why.id}

    for label, sheet_id, method, claim_type, target in (
        (
            "SIPOC 边界",
            sheet_ids["SIPOC"],
            "DOCUMENTED",
            "EXISTENCE",
            {"target_type": "ACTIVITY", "target_id": ids["a1_id"], "condition": "ALL"},
        ),
        (
            "VSM 观测等待",
            sheet_ids["VSM"],
            "OBSERVED",
            "TIME",
            {
                "target_type": "TIME_FIELD",
                "target_id": ids["a1_id"],
                "field": "wait",
                "condition": "ALL",
            },
        ),
        (
            "5Why 根因假设",
            sheet_ids["FIVE-WHY"],
            "STATED",
            "CONTROL",
            {"target_type": "ACTIVITY", "target_id": ids["a1_id"], "condition": "ALL"},
        ),
    ):
        response = client.post(
            f"{API}/processes/{pid}/evidence-claims",
            json={
                "claim": label,
                "claim_type": claim_type,
                "source_type": "TOOL_SHEET",
                "source_id": sheet_id,
                "method": method,
                "samples": 5 if method == "OBSERVED" else None,
                "targets": [target],
            },
        )
        assert response.status_code == 200, response.text

    claims = client.get(f"{API}/processes/{pid}/evidence-claims").json()
    conflict = next(item for item in claims["claims"] if item["conflict_group"] == "CG-TEST")
    adjudicated = client.post(
        f"{API}/processes/{pid}/evidence-claims/{conflict['id']}/adjudicate",
        json={"decision": "ACCEPT_DOCUMENT", "rationale": "以现行制度为准"},
    )
    assert adjudicated.status_code == 200, adjudicated.text

    after = client.get(f"{API}/processes/{pid}/r1-readiness").json()
    assert after["can_submit_review"] is True
    assert after["missing_inputs"] == []
    assert all(row["ready"] for row in after["inputs"] if row["required"])

    moved = client.post(
        f"{API}/asset-packages/{package['version_id']}/transition",
        json={"status": "IN_REVIEW"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "IN_REVIEW"


def test_traceability_matrix(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    suffix = uuid4().hex[:8]
    objective_id = kpi_id = orphan_id = None
    try:
        with SessionLocal() as db:
            objective = StrategyObjective(
                code=f"OBJ-T{suffix}",
                name="缩短交付周期",
                year=2026,
                period="ANNUAL",
                status="ACTIVE",
                unit="天",
            )
            db.add(objective)
            db.flush()
            kpi = KpiDefinition(
                code=f"KPI-T{suffix}",
                name="订单交付周期",
                dimension="EFFICIENCY",
                kind="PROCESS",
                direction="LOWER_BETTER",
                unit="天",
                process_id=pid,
                activity_id=ids["a1_id"],
            )
            db.add(kpi)
            db.flush()
            db.add(ObjectiveProcessLink(objective_id=objective.id, process_id=pid, kpi_id=kpi.id))
            db.add(KpiRecord(kpi_id=kpi.id, period=date(2026, 10, 1), value=12.5))
            orphan = StrategyObjective(
                code=f"OBJ-O{suffix}",
                name="未承接目标",
                year=2026,
                period="ANNUAL",
                status="ACTIVE",
            )
            db.add(orphan)
            db.commit()
            objective_id, kpi_id, orphan_id = objective.id, kpi.id, orphan.id

        _commit_package(client, pid)

        by_objective = client.get(f"{API}/traceability?objective_id={objective_id}")
        assert by_objective.status_code == 200, by_objective.text
        data = by_objective.json()
        assert data["summary"]["objectives"] >= 1
        assert data["summary"]["kpis"] >= 1
        assert data["summary"]["processes"] >= 1
        assert data["summary"]["activities"] >= 1
        assert data["summary"]["asset_versions"] >= 1
        assert data["summary"]["claims"] >= 1
        row = next(item for item in data["rows"] if item["activity_id"] == ids["a1_id"])
        assert row["kpi"]["code"] == f"KPI-T{suffix}"
        assert row["kpi"]["latest_value"] == 12.5
        assert row["node_keys"]
        assert row["assets"]
        assert row["claims"]

        by_process = client.get(f"{API}/traceability?process_id={pid}")
        assert by_process.status_code == 200
        assert by_process.json()["rows"]

        by_kpi = client.get(f"{API}/traceability?kpi_id={kpi_id}")
        assert by_kpi.status_code == 200
        assert by_kpi.json()["rows"]

        by_activity = client.get(f"{API}/traceability?activity_id={ids['a1_id']}")
        assert by_activity.status_code == 200
        assert all(item["activity_id"] == ids["a1_id"] for item in by_activity.json()["rows"])

        orphan_data = client.get(f"{API}/traceability?objective_id={orphan_id}").json()
        assert orphan_data["rows"] == []
        assert any(
            item["kind"] == "OBJECTIVE" and "未承接" in item["reason"]
            for item in orphan_data["orphans"]
        )
    finally:
        with SessionLocal() as db:
            db.execute(delete(ObjectiveProcessLink).where(ObjectiveProcessLink.process_id == pid))
            if kpi_id:
                db.execute(delete(KpiRecord).where(KpiRecord.kpi_id == kpi_id))
                db.execute(delete(KpiDefinition).where(KpiDefinition.id == kpi_id))
            for ident in (objective_id, orphan_id):
                if ident:
                    db.execute(delete(StrategyObjective).where(StrategyObjective.id == ident))
            db.commit()


def _upload_log(client, pid: int, csv_text: str, name: str = "log.csv") -> dict:
    response = client.post(
        f"{API}/processes/{pid}/log-imports",
        files={"file": (name, csv_text, "text/csv")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _map_and_commit(client, pid: int, import_id: int, mapping: dict) -> dict:
    mapped = client.post(
        f"{API}/processes/{pid}/log-imports/{import_id}/map",
        json={"mapping": mapping},
    )
    assert mapped.status_code == 200, mapped.text
    committed = client.post(f"{API}/processes/{pid}/log-imports/{import_id}/commit")
    assert committed.status_code == 200, committed.text
    return committed.json()


def _log_csv(prefix: str, count: int, month: int, lead_minutes: int) -> str:
    rows = ["case_id,activity,timestamp"]
    base = datetime(2026, month, 1, 9, 0)
    for index in range(count):
        started = base + timedelta(days=index)
        rows.append(f"{prefix}{index},接收订单,{started.isoformat()}")
        rows.append(
            f"{prefix}{index},信用检查,{(started + timedelta(minutes=lead_minutes)).isoformat()}"
        )
    return "\n".join(rows) + "\n"


def test_log_import_compare(client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before_csv = (
        "case_id,activity,timestamp\n"
        "C1,接收订单,2026-10-01T09:00:00\n"
        "C1,信用检查,2026-10-01T10:00:00\n"
        "C2,接收订单,2026-10-02T09:00:00\n"
        "C2,信用检查,2026-10-02T11:00:00\n"
    )
    after_csv = (
        "case_id,activity,timestamp\n"
        "D1,接收订单,2026-11-01T09:00:00\n"
        "D1,信用检查,2026-11-01T09:30:00\n"
        "D2,接收订单,2026-11-02T09:00:00\n"
        "D2,信用检查,2026-11-02T10:00:00\n"
    )
    before = _upload_log(client, pid, before_csv, "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    after = _upload_log(client, pid, after_csv, "after.csv")
    _map_and_commit(client, pid, after["id"], mapping)

    compared = client.get(
        f"{API}/processes/{pid}/log-imports/compare?before_id={before['id']}&after_id={after['id']}"
    )
    assert compared.status_code == 200, compared.text
    data = compared.json()
    assert data["comparable"] is True
    assert data["metrics"]["mean_lead_minutes"]["before"] == 90.0
    assert data["metrics"]["mean_lead_minutes"]["after"] == 45.0
    assert data["metrics"]["mean_lead_minutes"]["delta"] == -45.0
    assert data["metrics"]["mean_lead_minutes"]["delta_pct"] == -0.5
    assert "下降" in data["conclusion"]
    assert data["variants"]["before"] and data["variants"]["after"]

    different = _upload_log(client, pid, after_csv, "different.csv")
    _map_and_commit(
        client,
        pid,
        different["id"],
        {"接收订单": ids["a1_id"], "信用检查": ids["a3_id"]},
    )
    mismatch = client.get(
        f"{API}/processes/{pid}/log-imports/compare"
        f"?before_id={before['id']}&after_id={different['id']}"
    )
    assert mismatch.status_code == 200
    assert mismatch.json()["comparable"] is False
    assert any("映射不同" in item for item in mismatch.json()["reasons"])

    pending = _upload_log(client, pid, after_csv, "pending.csv")
    client.post(
        f"{API}/processes/{pid}/log-imports/{pending['id']}/map",
        json={"mapping": mapping},
    )
    not_committed = client.get(
        f"{API}/processes/{pid}/log-imports/compare"
        f"?before_id={before['id']}&after_id={pending['id']}"
    )
    assert not_committed.status_code == 200
    assert not_committed.json()["comparable"] is False
    assert any("提交为实测证据" in item for item in not_committed.json()["reasons"])

    assert (
        client.get(
            f"{API}/processes/{pid}/log-imports/compare"
            f"?before_id={before['id']}&after_id={before['id']}"
        ).status_code
        == 400
    )
    assert (
        client.get(
            f"{API}/processes/{pid}/log-imports/compare?before_id={before['id']}&after_id=99999999"
        ).status_code
        == 404
    )


def test_log_comparison_receipt_gate(client, manager_client, viewer_client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before = _upload_log(client, pid, _log_csv("C", 5, 10, 90), "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    after = _upload_log(client, pid, _log_csv("D", 5, 11, 45), "after.csv")
    _map_and_commit(client, pid, after["id"], mapping)
    query = f"before_id={before['id']}&after_id={after['id']}"

    compared = client.get(f"{API}/processes/{pid}/log-imports/compare?{query}")
    assert compared.status_code == 200, compared.text
    assert compared.json()["comparable"] is True

    readiness = client.get(f"{API}/processes/{pid}/log-imports/compare/claim-readiness?{query}")
    assert readiness.status_code == 200, readiness.text
    assert readiness.json()["claim_allowed"] is False
    assert readiness.json()["latest_receipt"] is None
    assert any("尚未接收" in item for item in readiness.json()["reasons"])

    forbidden = viewer_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "同意",
        },
    )
    assert forbidden.status_code == 403, forbidden.text

    blank = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "   ",
        },
    )
    assert blank.status_code == 400

    accepted = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "映射一致、窗口不重叠，接收为描述性对照",
        },
    )
    assert accepted.status_code == 200, accepted.text
    receipt = accepted.json()
    assert receipt["decision"] == "ACCEPT"
    assert receipt["comparable"] is True
    assert receipt["sample_ok"] is True
    assert receipt["claim_allowed"] is True
    assert receipt["metrics"]["metrics"]["mean_lead_minutes"]["delta"] == -45.0
    assert receipt["accepted_by_name"]
    assert receipt["accepted_at"].endswith("+00:00")

    readiness = client.get(f"{API}/processes/{pid}/log-imports/compare/claim-readiness?{query}")
    assert readiness.status_code == 200
    assert readiness.json()["claim_allowed"] is True
    assert readiness.json()["reasons"] == []
    assert readiness.json()["latest_receipt"]["id"] == receipt["id"]

    returned = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "RETURN",
            "rationale": "覆盖不足，退回补充",
        },
    )
    assert returned.status_code == 200, returned.text
    assert returned.json()["claim_allowed"] is False

    readiness = client.get(f"{API}/processes/{pid}/log-imports/compare/claim-readiness?{query}")
    assert readiness.json()["claim_allowed"] is False
    assert readiness.json()["latest_receipt"]["decision"] == "RETURN"
    assert any("未被接收" in item for item in readiness.json()["reasons"])

    receipts = client.get(f"{API}/processes/{pid}/log-imports/compare/receipts?{query}")
    assert receipts.status_code == 200, receipts.text
    listed = receipts.json()
    assert [row["id"] for row in listed] == sorted(
        [receipt["id"], returned.json()["id"]], reverse=True
    )
    assert (
        client.get(
            f"{API}/processes/{pid}/log-imports/compare/receipts"
            f"?before_id={before['id']}&after_id=99999999"
        ).status_code
        == 404
    )

    different = _upload_log(client, pid, _log_csv("E", 5, 12, 45), "different.csv")
    _map_and_commit(
        client, pid, different["id"], {"接收订单": ids["a1_id"], "信用检查": ids["a3_id"]}
    )
    refused = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": different["id"],
            "decision": "ACCEPT",
            "rationale": "看起来差不多",
        },
    )
    assert refused.status_code == 400
    assert "不可比" in refused.text

    invalid_decision = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "APPROVE",
            "rationale": "同意",
        },
    )
    assert invalid_decision.status_code == 422

    missing = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": 99999999,
            "decision": "OBSERVE",
            "rationale": "先观察",
        },
    )
    assert missing.status_code == 404


def test_log_comparison_receipt_rejects_improvement_claim_on_small_sample(
    client, manager_client, asset_process
):
    ids = asset_process
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before = _upload_log(client, pid, _log_csv("C", 2, 10, 90), "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    after = _upload_log(client, pid, _log_csv("D", 2, 11, 45), "after.csv")
    _map_and_commit(client, pid, after["id"], mapping)
    query = f"before_id={before['id']}&after_id={after['id']}"

    accepted = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "接收为方向性观察",
        },
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["comparable"] is True
    assert accepted.json()["sample_ok"] is False
    assert accepted.json()["claim_allowed"] is False

    readiness = client.get(f"{API}/processes/{pid}/log-imports/compare/claim-readiness?{query}")
    assert readiness.status_code == 200
    assert readiness.json()["claim_allowed"] is False
    assert any("样本量不足" in item for item in readiness.json()["reasons"])


def _create_test_kpi(
    pid: int,
    suffix: str,
    unit: str = "分钟",
    activity_id: int | None = None,
    frequency: str = "MONTHLY",
) -> int:
    with SessionLocal() as db:
        kpi = KpiDefinition(
            code=f"KPI-WB-{suffix}",
            name="日志对照周期",
            dimension="EFFICIENCY",
            kind="PROCESS",
            direction="LOWER_BETTER",
            unit=unit,
            frequency=frequency,
            process_id=pid,
            activity_id=activity_id,
            is_active=True,
        )
        db.add(kpi)
        db.commit()
        db.refresh(kpi)
        return kpi.id


def _drop_test_kpi(kpi_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(KpiRecord).where(KpiRecord.kpi_id == kpi_id))
        db.execute(delete(KpiDefinition).where(KpiDefinition.id == kpi_id))
        db.commit()


def _accepted_log_pair(client, manager_client, ids: dict) -> tuple[int, int]:
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before = _upload_log(client, pid, _log_csv("C", 5, 10, 90), "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    after = _upload_log(client, pid, _log_csv("D", 5, 11, 45), "after.csv")
    _map_and_commit(client, pid, after["id"], mapping)
    accepted = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "映射一致、窗口不重叠",
        },
    )
    assert accepted.status_code == 200, accepted.text
    return before["id"], after["id"]


def test_log_comparison_write_back_requires_accepted_comparison(
    client, manager_client, asset_process
):
    ids = asset_process
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before = _upload_log(client, pid, _log_csv("C", 5, 10, 90), "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    after = _upload_log(client, pid, _log_csv("D", 5, 11, 45), "after.csv")
    _map_and_commit(client, pid, after["id"], mapping)
    query = f"before_id={before['id']}&after_id={after['id']}"
    kpi_id = _create_test_kpi(pid, uuid4().hex[:6])
    try:
        options = client.get(
            f"{API}/processes/{pid}/log-imports/compare/write-back-options?{query}"
        )
        assert options.status_code == 200, options.text
        assert options.json()["claim_allowed"] is False
        assert any("尚未接收" in item for item in options.json()["reasons"])

        refused = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before["id"],
                "after_id": after["id"],
                "kpi_id": kpi_id,
                "update_baseline": True,
                "target_value": 30,
                "rationale": "直接写回",
            },
        )
        assert refused.status_code == 409, refused.text
        assert "可写回条件" in refused.text
    finally:
        _drop_test_kpi(kpi_id)


def test_log_comparison_write_back_updates_kpi_with_version_and_evidence(
    client, manager_client, asset_process
):
    ids = asset_process
    pid = ids["process_id"]
    before_id, after_id = _accepted_log_pair(client, manager_client, ids)
    query = f"before_id={before_id}&after_id={after_id}"
    suffix = uuid4().hex[:6]
    kpi_min = _create_test_kpi(pid, suffix, unit="分钟")
    kpi_hour = _create_test_kpi(pid, suffix + "h", unit="小时")
    kpi_bad = _create_test_kpi(pid, suffix + "n", unit="个")
    kpi_activity = _create_test_kpi(pid, suffix + "a", activity_id=ids["a1_id"])
    kpi_weekly = _create_test_kpi(pid, suffix + "w", frequency="WEEKLY")
    kpi_formal = _create_test_kpi(pid, suffix + "f", unit="分钟")
    try:
        options = client.get(
            f"{API}/processes/{pid}/log-imports/compare/write-back-options?{query}"
        )
        assert options.status_code == 200, options.text
        body = options.json()
        assert body["claim_allowed"] is True
        by_id = {row["kpi_id"]: row for row in body["kpis"]}
        assert by_id[kpi_min]["observed_value"] == 45.0
        assert by_id[kpi_min]["observed_period"] == "2026-11-01"
        assert by_id[kpi_hour]["observed_value"] == 0.75
        assert kpi_bad not in by_id
        assert kpi_activity not in by_id
        assert kpi_weekly not in by_id

        written = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_min,
                "update_baseline": True,
                "target_value": 30,
                "rationale": "接收后以实测平均周期更新基线，目标由管理科另行确定",
            },
        )
        assert written.status_code == 200, written.text
        result = written.json()
        assert result["baseline_before"] is None
        assert result["baseline_after"] == 45.0
        assert result["target_before"] is None
        assert result["target_after"] == 30.0
        assert result["kpi_version_before"] == 1
        assert result["kpi_version_after"] == 2
        assert result["record_value"] == 45.0
        assert result["record_period"] == "2026-11-01"
        assert result["claim_allowed"] is True

        with SessionLocal() as db:
            kpi = db.get(KpiDefinition, kpi_min)
            assert kpi.baseline_value == 45.0
            assert kpi.target_value == 30.0
            assert kpi.version == 2
            record = db.scalar(select(KpiRecord).where(KpiRecord.kpi_id == kpi_min))
            assert record.value == 45.0
            provenance = record.provenance
            assert provenance["source_kind"] == "LOG_COMPARISON"
            assert provenance["comparison_receipt_id"] == result["receipt_id"]
            assert provenance["after_import_id"] == after_id
            assert provenance["compared_metric"] == "mean_lead_minutes"
            assert provenance["metrics"]["mean_lead_minutes"]["delta"] == -45.0

        repeated = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_min,
                "update_baseline": True,
                "target_value": 30,
                "rationale": "接收后以实测平均周期更新基线，目标由管理科另行确定",
            },
        )
        assert repeated.status_code == 200, repeated.text
        assert repeated.json()["kpi_version_after"] == 2
        assert repeated.json()["record_revision"] == result["record_revision"]

        hourly = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_hour,
                "update_baseline": True,
                "target_value": None,
                "rationale": "按小时口径写回",
            },
        )
        assert hourly.status_code == 200, hourly.text
        assert hourly.json()["baseline_after"] == 0.75
        assert hourly.json()["record_value"] == 0.75

        unit_refused = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_bad,
                "update_baseline": True,
                "rationale": "按个数写回",
            },
        )
        assert unit_refused.status_code == 400
        assert "时长" in unit_refused.text

        activity_refused = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_activity,
                "update_baseline": True,
                "rationale": "按活动写回",
            },
        )
        assert activity_refused.status_code == 400
        assert "流程级" in activity_refused.text

        weekly_refused = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_weekly,
                "update_baseline": True,
                "rationale": "按周频写回",
            },
        )
        assert weekly_refused.status_code == 400
        assert "月频" in weekly_refused.text

        with SessionLocal() as db:
            db.add(
                KpiRecord(
                    kpi_id=kpi_formal,
                    period=date(2026, 11, 1),
                    value=50.0,
                    note="正式月报",
                    provenance={"source_kind": "MANUAL", "quality": "UNKNOWN"},
                )
            )
            db.commit()
        conflict = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_formal,
                "update_baseline": True,
                "rationale": "覆盖正式月报",
            },
        )
        assert conflict.status_code == 409
        assert "正式数据点" in conflict.text

        blank = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "kpi_id": kpi_min,
                "update_baseline": True,
                "rationale": "   ",
            },
        )
        assert blank.status_code == 400
    finally:
        for kpi_id in (kpi_min, kpi_hour, kpi_bad, kpi_activity, kpi_weekly, kpi_formal):
            _drop_test_kpi(kpi_id)


def test_log_comparison_write_back_rejects_cross_month_window(
    client, manager_client, asset_process
):
    ids = asset_process
    pid = ids["process_id"]
    mapping = {"接收订单": ids["a1_id"], "信用检查": ids["a2_id"]}
    before = _upload_log(client, pid, _log_csv("C", 5, 10, 90), "before.csv")
    _map_and_commit(client, pid, before["id"], mapping)
    cross_csv = (
        "case_id,activity,timestamp\n"
        "X0,接收订单,2026-10-30T09:00:00\nX0,信用检查,2026-10-30T10:30:00\n"
        "X1,接收订单,2026-10-31T09:00:00\nX1,信用检查,2026-10-31T10:30:00\n"
        "X2,接收订单,2026-11-01T09:00:00\nX2,信用检查,2026-11-01T10:30:00\n"
        "X3,接收订单,2026-11-02T09:00:00\nX3,信用检查,2026-11-02T10:30:00\n"
        "X4,接收订单,2026-11-03T09:00:00\nX4,信用检查,2026-11-03T10:30:00\n"
    )
    after = _upload_log(client, pid, cross_csv, "cross.csv")
    _map_and_commit(client, pid, after["id"], mapping)
    accepted = manager_client.post(
        f"{API}/processes/{pid}/log-imports/compare/receipt",
        json={
            "before_id": before["id"],
            "after_id": after["id"],
            "decision": "ACCEPT",
            "rationale": "窗口跨月，仍接收为方向性观察",
        },
    )
    assert accepted.status_code == 200, accepted.text
    kpi_id = _create_test_kpi(pid, uuid4().hex[:6])
    try:
        refused = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/write-back",
            json={
                "before_id": before["id"],
                "after_id": after["id"],
                "kpi_id": kpi_id,
                "update_baseline": True,
                "rationale": "跨月窗口写回",
            },
        )
        assert refused.status_code == 409, refused.text
        assert "跨月" in refused.text
    finally:
        _drop_test_kpi(kpi_id)


def _create_gate_project(pid: int, suffix: str) -> int:
    with SessionLocal() as db:
        project = Project(
            code=f"PRJ-WB-{suffix}",
            name="门禁对照测试项目",
            methodology="BPI",
            owner="测试",
            process_id=pid,
            current_stage=1,
            gate_required=True,
        )
        db.add(project)
        db.commit()
        db.refresh(project)
        return project.id


def _drop_gate_project(project_id: int) -> None:
    with SessionLocal() as db:
        db.execute(delete(GateAttestation).where(GateAttestation.project_id == project_id))
        db.execute(delete(Project).where(Project.id == project_id))
        db.commit()


def test_stage_gate_requires_accepted_comparison(client, manager_client, asset_process):
    ids = asset_process
    pid = ids["process_id"]
    before_id, after_id = _accepted_log_pair(client, manager_client, ids)
    query = f"before_id={before_id}&after_id={after_id}"
    receipt_id = client.get(f"{API}/processes/{pid}/log-imports/compare/receipts?{query}").json()[
        0
    ]["id"]
    project_id = _create_gate_project(pid, uuid4().hex[:6])
    base_gate = {
        "project_id": project_id,
        "stage_no": 1,
        "conclusion": "PASS",
        "evidence_url": "https://example.com/improvement-gate.pdf",
    }
    try:
        accepted = client.get(f"{API}/processes/{pid}/log-imports/compare/accepted")
        assert accepted.status_code == 200, accepted.text
        assert any(row["receipt_id"] == receipt_id for row in accepted.json())

        missing = manager_client.post(
            f"{API}/maturity/gates",
            json={**base_gate, "claims_improvement": True},
        )
        assert missing.status_code == 400, missing.text
        assert "已接收的对照" in missing.text

        foreign = manager_client.post(
            f"{API}/maturity/gates",
            json={
                **base_gate,
                "claims_improvement": True,
                "comparison_receipt_id": 99999999,
            },
        )
        assert foreign.status_code == 400, foreign.text
        assert "不属于本项目流程" in foreign.text

        signed = manager_client.post(
            f"{API}/maturity/gates",
            json={
                **base_gate,
                "claims_improvement": True,
                "comparison_receipt_id": receipt_id,
            },
        )
        assert signed.status_code == 201, signed.text
        body = signed.json()
        assert body["claims_improvement"] is True
        assert body["comparison_receipt_id"] == receipt_id
        assert body["evidence_snapshot"]["kind"] == "LOG_COMPARISON"
        assert body["evidence_snapshot"]["metrics"]["mean_lead_minutes"]["delta"] == -45.0
        assert body["evidence_snapshot"]["sample_ok"] is True

        with SessionLocal() as db:
            project = db.get(Project, project_id)
            maturity_service.ensure_advance_allowed(db, project, 2)

        returned = manager_client.post(
            f"{API}/processes/{pid}/log-imports/compare/receipt",
            json={
                "before_id": before_id,
                "after_id": after_id,
                "decision": "RETURN",
                "rationale": "复核后认为证据不足，退回补充",
            },
        )
        assert returned.status_code == 200, returned.text

        with SessionLocal() as db:
            project = db.get(Project, project_id)
            with pytest.raises(maturity_service.MaturityError) as exc:
                maturity_service.ensure_advance_allowed(db, project, 2)
            assert "对照已失效" in str(exc.value)

        stale = manager_client.post(
            f"{API}/maturity/gates",
            json={
                **base_gate,
                "claims_improvement": True,
                "comparison_receipt_id": receipt_id,
            },
        )
        assert stale.status_code == 400, stale.text
        assert "未达到可核验条件" in stale.text

        accepted = client.get(f"{API}/processes/{pid}/log-imports/compare/accepted")
        assert accepted.status_code == 200
        assert not any(row["receipt_id"] == receipt_id for row in accepted.json())
    finally:
        _drop_gate_project(project_id)
