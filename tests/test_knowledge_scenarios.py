"""场景驱动知识库：场景、推荐、使用证据与求真审核。"""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.core.database import SessionLocal
from app.core.timeutil import utcnow
from app.models.knowledge import KnowledgeItem
from app.models.process_document import ProcessDocument, ProcessDocumentVersion

API = "/api/v1"


def _create_draft(client, **overrides):
    code = uuid.uuid4().hex[:6].upper()
    payload = {
        "title": f"知识测试-{code}",
        "type": "METHOD",
        "summary": "测试用知识摘要",
        "content": "测试正文：用于验证场景推荐与审核链路。",
        "claim": "解决流程责任不清的问题",
        "applicable_when": "跨部门流程定责时使用",
        "not_applicable_when": "强制制度条款应走制度中心",
        "evidence_summary": "测试部门使用后争议减少",
        "scenario_codes": ["RACI"],
    }
    payload.update(overrides)
    created = client.post(f"{API}/knowledge", json=payload)
    assert created.status_code == 201, created.text
    return created.json()


def _submit_and_approve(client, item_id: int) -> dict:
    submitted = client.post(f"{API}/knowledge/{item_id}/submit")
    assert submitted.status_code == 200, submitted.text
    approved = client.post(f"{API}/knowledge/{item_id}/review", json={"decision": "APPROVE"})
    assert approved.status_code == 200, approved.text
    return approved.json()


def test_scenarios_and_meta(client):
    scenarios = client.get(f"{API}/knowledge/scenarios").json()
    assert {row["code"] for row in scenarios} == {
        "FLOW",
        "CYCLE",
        "ERROR",
        "RACI",
        "COST",
        "STANDARD",
    }

    meta = client.get(f"{API}/knowledge/meta").json()
    assert len(meta["scenarios"]) == 6
    assert meta["stats"]["total"] >= 1
    assert meta["stats"]["verified"] >= 1
    assert meta["type_labels"]["METHOD"] == "方法"
    assert meta["status_labels"]["VERIFIED"] == "已验证"


def test_recommend_by_scenario_returns_explainable_items(client):
    result = client.post(
        f"{API}/knowledge/recommend", json={"scenario_codes": ["RACI"], "limit": 8}
    )
    assert result.status_code == 200, result.text
    items = result.json()["items"]
    assert items, "责任不清场景没有推荐结果"
    top_titles = [item["title"] for item in items]
    assert any("RACI" in title for title in top_titles), top_titles
    assert any("场景" in reason for reason in items[0]["matched_on"]), items[0]

    knowledge = next(row for row in items if row["kind"] == "knowledge")
    assert knowledge["links"]["detail"].startswith("/knowledge/")
    tool = next((row for row in items if row["kind"] == "tool"), None)
    assert tool is not None, "统一推荐没有返回工具"
    assert tool["code"]
    assert tool["links"]["detail"].startswith("/toolbox?open=")


def test_primary_step_link(client):
    item = _create_draft(client, stage_no=1, step_no="1.1", is_primary=True)
    try:
        detail = client.get(f"{API}/knowledge/{item['id']}").json()
        assert detail["primary_step_nos"] == ["1.1"]
        updated = client.patch(f"{API}/knowledge/{item['id']}", json={"is_primary": False})
        assert updated.status_code == 200, updated.text
        assert updated.json()["primary_step_nos"] == []
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_tool_guide_requires_existing_tool(client):
    base = {
        "title": "工具指南测试",
        "type": "TOOL",
        "summary": "测试工具指南",
        "content": "正文",
        "claim": "验证工具引用",
        "applicable_when": "测试",
        "not_applicable_when": "测试",
        "scenario_codes": ["FLOW"],
    }
    missing = client.post(f"{API}/knowledge", json=base)
    assert missing.status_code == 400, missing.text
    assert "工具编码" in missing.json()["detail"]

    unknown = client.post(f"{API}/knowledge", json={**base, "tool_code": "NO-SUCH-TOOL"})
    assert unknown.status_code == 400, unknown.text
    assert "不存在" in unknown.json()["detail"]

    valid = client.post(f"{API}/knowledge", json={**base, "tool_code": "VSM"})
    assert valid.status_code == 201, valid.text
    assert client.delete(f"{API}/knowledge/{valid.json()['id']}").status_code == 200


def test_usage_evidence_changes_score(client):
    item = _create_draft(client)
    _submit_and_approve(client, item["id"])
    try:
        before = client.post(
            f"{API}/knowledge/recommend",
            json={"scenario_codes": ["RACI"], "limit": 20},
        ).json()["items"]
        before_score = next(row["score"] for row in before if row["id"] == item["id"])

        for index in range(3):
            recorded = client.post(
                f"{API}/knowledge/{item['id']}/usage",
                json={
                    "outcome": "EFFECTIVE",
                    "note": "测试使用有效",
                    "step_no": f"1.{index + 1}",
                },
            )
            assert recorded.status_code == 201, recorded.text

        after = client.post(
            f"{API}/knowledge/recommend",
            json={"scenario_codes": ["RACI"], "limit": 20},
        ).json()["items"]
        row = next(row for row in after if row["id"] == item["id"])
        assert row["used_count"] == 3
        assert row["effective_count"] == 3
        assert row["score"] > before_score, "使用证据没有改变推荐分"

        detail = client.get(f"{API}/knowledge/{item['id']}").json()
        assert detail["used_count"] == 3
        assert detail["effectiveness_rate"] == 100.0
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_review_gate_blocks_incomplete_draft(client, viewer_client):
    created = client.post(
        f"{API}/knowledge",
        json={
            "title": "不完整草稿",
            "type": "CASE",
            "summary": "缺字段的草稿",
            "content": "正文",
            "scenario_codes": ["FLOW"],
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    try:
        rejected = client.post(f"{API}/knowledge/{item_id}/submit")
        assert rejected.status_code == 400
        assert "主张" in rejected.json()["detail"]

        client.patch(
            f"{API}/knowledge/{item_id}",
            json={
                "claim": "解决流程混乱",
                "applicable_when": "流程环节不清时",
                "not_applicable_when": "已有正式制度时",
                "evidence_summary": "测试部门用过，交接减少",
            },
        )
        submitted = client.post(f"{API}/knowledge/{item_id}/submit")
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "IN_REVIEW"

        # 未审核条目不进入普通列表，但 Manager 可以按状态筛选
        visible = client.get(f"{API}/knowledge", params={"keyword": "不完整草稿"}).json()
        assert visible["total"] == 0
        pending = client.get(
            f"{API}/knowledge", params={"status": "IN_REVIEW", "keyword": "不完整草稿"}
        ).json()
        assert pending["total"] == 1

        assert viewer_client.delete(f"{API}/knowledge/{item_id}").status_code == 403
    finally:
        assert client.delete(f"{API}/knowledge/{item_id}").status_code == 200


def test_workflow_step_recommendations_include_knowledge(client):
    result = client.get(f"{API}/workflow/steps/1.1/recommendations")
    assert result.status_code == 200, result.text
    body = result.json()
    assert "knowledge" in body
    assert body["knowledge"], "阶段 1 没有推送知识"
    assert all(row["kind"] == "knowledge" for row in body["knowledge"])


def test_workflow_stages_expose_knowledge_count(client):
    stages = client.get(f"{API}/workflow/stages").json()
    steps = {step["step_no"]: step for stage in stages for step in stage["steps"]}
    assert steps["1.1"]["knowledge_count"] >= 1, "阶段 1 的步骤应显示推荐知识数"
    flat = client.get(f"{API}/workflow/steps", params={"stage_no": 1}).json()
    assert all("knowledge_count" in row for row in flat)
    stage_rows = {row["stage_no"]: row for row in stages}
    assert stage_rows[1]["knowledge_count"] >= 1, "阶段入口没有汇总知识数"
    assert all("knowledge_count" in row for row in stages)


def test_standard_type_is_rejected(client):
    created = client.post(
        f"{API}/knowledge",
        json={
            "title": "不应创建的制度条目",
            "type": "STANDARD",
            "summary": "制度应走制度中心",
            "content": "正文",
            "scenario_codes": ["STANDARD"],
        },
    )
    assert created.status_code == 400, created.text
    assert "流程标准文件" in created.json()["detail"]

    item = _create_draft(client)
    try:
        updated = client.patch(f"{API}/knowledge/{item['id']}", json={"type": "STANDARD"})
        assert updated.status_code == 400, updated.text
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_usage_step_context_and_short_term_dedupe(client):
    item = _create_draft(client)
    _submit_and_approve(client, item["id"])
    try:
        payload = {"outcome": "EFFECTIVE", "step_no": "1.2", "note": "步骤上下文测试"}
        first = client.post(f"{API}/knowledge/{item['id']}/usage", json=payload)
        assert first.status_code == 201, first.text
        second = client.post(f"{API}/knowledge/{item['id']}/usage", json=payload)
        assert second.status_code == 201, second.text
        assert second.json()["id"] == first.json()["id"], "短期重复提交没有去重"
        assert second.json()["step_no"] == "1.2"

        rows = client.get(f"{API}/knowledge/{item['id']}/usage").json()
        assert len(rows) == 1

        # 不同步骤属于不同使用场景，应各记一次
        other = client.post(
            f"{API}/knowledge/{item['id']}/usage",
            json={**payload, "step_no": "1.3"},
        )
        assert other.status_code == 201
        assert other.json()["id"] != first.json()["id"]
        assert len(client.get(f"{API}/knowledge/{item['id']}/usage").json()) == 2
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_new_knowledge_can_link_specific_step(client):
    item = _create_draft(client, stage_no=1, step_no="1.1")
    try:
        detail = client.get(f"{API}/knowledge/{item['id']}").json()
        assert detail["stage_nos"] == [1]
        assert detail["step_nos"] == ["1.1"]
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_fulltext_search_matches_content(client):
    item = _create_draft(client)
    try:
        _submit_and_approve(client, item["id"])
        rows = client.get(f"{API}/knowledge", params={"keyword": "场景推荐"}).json()
        assert any(row["id"] == item["id"] for row in rows["items"]), "全文检索没有命中文档正文"
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_review_history_records_decisions(client):
    item = _create_draft(client)
    try:
        _submit_and_approve(client, item["id"])
        reviews = client.get(f"{API}/knowledge/{item['id']}/reviews").json()
        assert reviews
        assert reviews[0]["decision"] == "APPROVE"
        assert reviews[0]["decision_label"] == "通过"
        assert reviews[0]["from_status"] == "IN_REVIEW"
        assert reviews[0]["to_status"] == "VERIFIED"
        assert reviews[0]["reviewer"]
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_scenario_admin_crud(client, viewer_client):
    code = "E2E" + uuid.uuid4().hex[:6].upper()
    created = client.post(
        f"{API}/knowledge/scenarios",
        json={"code": code, "name": "测试场景", "description": "临时场景", "sort_order": 99},
    )
    assert created.status_code == 201, created.text
    scenario_id = created.json()["id"]
    try:
        updated = client.patch(
            f"{API}/knowledge/scenarios/{scenario_id}",
            json={"name": "测试场景改", "is_active": False},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "测试场景改"
        assert updated.json()["is_active"] is False

        all_rows = client.get(
            f"{API}/knowledge/scenarios", params={"include_inactive": True}
        ).json()
        assert any(row["id"] == scenario_id for row in all_rows)
        active_codes = {row["code"] for row in client.get(f"{API}/knowledge/scenarios").json()}
        assert code not in active_codes

        assert (
            viewer_client.post(
                f"{API}/knowledge/scenarios",
                json={"code": code + "X", "name": "越权场景"},
            ).status_code
            == 403
        )
    finally:
        client.patch(f"{API}/knowledge/scenarios/{scenario_id}", json={"is_active": False})


def test_recommend_log_is_auditable(client, viewer_client):
    problem = "推荐日志测试 " + uuid.uuid4().hex[:6]
    result = client.post(
        f"{API}/knowledge/recommend",
        json={"problem": problem, "scenario_codes": ["RACI"], "limit": 10},
    )
    assert result.status_code == 200, result.text
    items = result.json()["items"]
    knowledge_ids = [row["id"] for row in items if row["kind"] == "knowledge"]

    logs = client.get(f"{API}/knowledge/recommend-logs").json()
    row = next((row for row in logs if row["problem"] == problem), None)
    assert row is not None, "推荐请求没有留下解释日志"
    assert row["result_ids"] == knowledge_ids
    assert row["result_refs"], "推荐日志缺少统一引用"
    assert any(ref["kind"] == "tool" for ref in row["result_refs"])
    assert row["user"]
    assert viewer_client.get(f"{API}/knowledge/recommend-logs").status_code == 403


def test_archived_standard_can_migrate_to_document(client):
    candidates = client.get(f"{API}/knowledge/standard-candidates").json()
    assert candidates, "种子数据里应有已归档的 STANDARD 知识"
    item = candidates[0]

    processes = client.get(f"{API}/process-map/flat").json()
    process_id = next(row["id"] for row in processes if row["code"] == "L3-032")
    migrated = client.post(
        f"{API}/knowledge/{item['id']}/migrate-to-document",
        json={"process_id": process_id, "category": "POLICY", "title": "迁移测试制度"},
    )
    assert migrated.status_code == 201, migrated.text
    body = migrated.json()
    assert body["document_code"].startswith("PD-")
    assert body["version_label"] == "1.0"

    document = client.get(f"{API}/process-documents/{body['document_id']}").json()
    assert document["title"] == "迁移测试制度"
    try:
        db = SessionLocal()
        try:
            db.query(ProcessDocumentVersion).filter(
                ProcessDocumentVersion.document_id == body["document_id"]
            ).delete()
            db.query(ProcessDocument).filter(ProcessDocument.id == body["document_id"]).delete()
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001 - 清理失败不影响功能断言
        pass


def _backdate(item_id: int, days: int = 400) -> None:
    db = SessionLocal()
    try:
        item = db.get(KnowledgeItem, item_id)
        stamp = utcnow() - timedelta(days=days)
        item.created_at = stamp
        item.updated_at = stamp
        db.commit()
    finally:
        db.close()


def _set_review_due(item_id: int, days: int = -1) -> None:
    db = SessionLocal()
    try:
        item = db.get(KnowledgeItem, item_id)
        item.review_due_at = utcnow().date() + timedelta(days=days)
        db.commit()
    finally:
        db.close()


def test_archive_candidates_and_archive(client, viewer_client):
    item = _create_draft(client)
    _submit_and_approve(client, item["id"])
    try:
        _backdate(item["id"])

        candidates = client.get(f"{API}/knowledge/archive-candidates").json()
        row = next((row for row in candidates if row["id"] == item["id"]), None)
        assert row is not None, "长期未使用的知识没有进入归档候选"
        assert row["unused_days"] >= 365

        assert viewer_client.get(f"{API}/knowledge/archive-candidates").status_code == 403

        archived = client.post(f"{API}/knowledge/{item['id']}/archive")
        assert archived.status_code == 200, archived.text
        assert archived.json()["status"] == "ARCHIVED"

        public = client.get(f"{API}/knowledge", params={"keyword": item["title"]}).json()
        assert public["total"] == 0, "归档条目仍出现在公开列表"
        recommended = client.post(
            f"{API}/knowledge/recommend", json={"scenario_codes": ["RACI"], "limit": 20}
        ).json()["items"]
        assert all(row["id"] != item["id"] for row in recommended), "归档条目仍被推荐"
        remaining = client.get(f"{API}/knowledge/archive-candidates").json()
        assert all(row["id"] != item["id"] for row in remaining)
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_best_practice_promotion_and_effect_stats(client, viewer_client):
    item = _create_draft(client)
    _submit_and_approve(client, item["id"])
    try:
        blocked = client.post(f"{API}/knowledge/{item['id']}/promote")
        assert blocked.status_code == 400, blocked.text
        assert "5 次" in blocked.json()["detail"]

        for index in range(5):
            recorded = client.post(
                f"{API}/knowledge/{item['id']}/usage",
                json={
                    "outcome": "EFFECTIVE",
                    "note": "晋升门槛测试",
                    "step_no": f"2.{index + 1}",
                },
            )
            assert recorded.status_code == 201, recorded.text

        promoted = client.post(f"{API}/knowledge/{item['id']}/promote")
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["is_best_practice"] is True

        stats = client.get(f"{API}/knowledge/effect-stats")
        assert stats.status_code == 200, stats.text
        body = stats.json()
        assert body["usage_total"] >= 5
        assert any(row["id"] == item["id"] for row in body["top_items"])
        assert any(row["type"] == "METHOD" for row in body["by_type"])
        assert viewer_client.get(f"{API}/knowledge/effect-stats").status_code == 403
        assert viewer_client.post(f"{API}/knowledge/{item['id']}/promote").status_code == 403
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200


def test_governance_scan_flags_overdue_knowledge(client):
    item = _create_draft(client)
    _submit_and_approve(client, item["id"])
    try:
        _set_review_due(item["id"], days=-1)
        scanned = client.post(f"{API}/baselines/audit-scan")
        assert scanned.status_code == 200, scanned.text

        findings = client.get(
            f"{API}/baselines/findings", params={"status": "OPEN", "limit": 200}
        ).json()
        finding = next(
            (
                row
                for row in findings
                if row["type"] == "KNOWLEDGE_REVIEW_OVERDUE"
                and row["entity_type"] == "knowledge"
                and row["entity_id"] == item["id"]
            ),
            None,
        )
        assert finding is not None, "已过复核日期的知识没有进入治理待办"
        assert finding["type_label"] == "知识待复核"
    finally:
        assert client.delete(f"{API}/knowledge/{item['id']}").status_code == 200
        client.post(f"{API}/baselines/audit-scan")
