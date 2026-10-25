"""问题驱动的工具箱：场景匹配、决策字段与工作流推荐。"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from app.core.database import SessionLocal
from app.models.tool import Tool

API = "/api/v1"


def test_tool_meta_has_scenarios_and_difficulty_labels(client):
    meta = client.get(f"{API}/tools/meta").json()
    assert {row["code"] for row in meta["scenarios"]} == {
        "FLOW",
        "CYCLE",
        "ERROR",
        "RACI",
        "COST",
        "STANDARD",
    }
    assert meta["difficulty_labels"]["LOW"] == "低"
    assert meta["category_labels"]["DIAGNOSE"] == "诊断工具"


def test_tool_detail_has_decision_fields_and_related_knowledge(client):
    detail = client.get(f"{API}/tools/VSM").json()
    assert detail["verification_standard"], "VSM 缺少验证标准"
    assert detail["not_applicable_when"], "VSM 缺少不适用条件"
    assert detail["prerequisites"], "VSM 缺少前置条件"
    assert detail["difficulty_label"] == "中"
    assert "CYCLE" in detail["scenario_codes"]
    assert detail["usage"]["used"] >= 3
    assert detail["knowledge"], "VSM 没有关联知识"
    assert detail["knowledge_count"] >= len(detail["knowledge"])
    assert detail["workflow_steps"], "VSM 没有被步骤契约引用"


def test_tool_match_by_scenario(client):
    result = client.post(f"{API}/tools/match", json={"scenario_codes": ["CYCLE"], "limit": 10})
    assert result.status_code == 200, result.text
    hits = result.json()["hits"]
    codes = [hit["tool"]["code"] for hit in hits]
    assert "VSM" in codes, codes
    top = hits[0]
    assert 0 <= top["score"] <= 99
    assert any("场景" in reason for reason in top["matched_on"])
    assert top["verification_standard"], "推荐结果缺少验证标准"
    assert top["usage"]["used"] >= 0
    assert "knowledge_count" in top["tool"]


def test_tool_match_category_filter(client):
    result = client.post(
        f"{API}/tools/match",
        json={"problem": "审批太多，周期太长", "category_filters": ["DIAGNOSE"]},
    )
    hits = result.json()["hits"]
    assert hits
    assert all(hit["tool"]["category"] == "DIAGNOSE" for hit in hits)


def test_tool_match_no_result(client):
    result = client.post(f"{API}/tools/match", json={"problem": "qwertyuiop"})
    assert result.json()["hits"] == [], "无关输入不应靠证据分硬凑结果"


def test_tool_match_sort_by_difficulty(client):
    result = client.post(
        f"{API}/tools/match",
        json={"scenario_codes": ["CYCLE"], "sort": "difficulty", "limit": 10},
    )
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    values = [order[hit["tool"]["difficulty"]] for hit in result.json()["hits"]]
    assert values == sorted(values)


def test_workflow_step_recommendation_has_why_and_verification(client):
    result = client.get(f"{API}/workflow/steps/2.1/recommendations")
    assert result.status_code == 200, result.text
    tools = result.json()["tools"]
    assert tools
    sipoc = next((row for row in tools if row["code"] == "SIPOC"), None)
    assert sipoc is not None, [row["code"] for row in tools]
    assert sipoc["why"]
    assert sipoc["verification_standard"]
    assert sipoc["difficulty_label"] == "低"


def test_tool_review_overdue_flag_and_governance(client):
    db = SessionLocal()
    try:
        tool = db.query(Tool).filter(Tool.code == "VSM").one()
        original = tool.review_due_at
        tool.review_due_at = date.today() - timedelta(days=1)
        db.commit()
    finally:
        db.close()

    try:
        detail = client.get(f"{API}/tools/VSM").json()
        assert detail["review_overdue"] is True
        assert detail["review_due_at"] == (date.today() - timedelta(days=1)).isoformat()

        assert client.post(f"{API}/baselines/audit-scan").status_code == 200
        findings = client.get(
            f"{API}/baselines/findings", params={"status": "OPEN", "limit": 200}
        ).json()
        assert any(
            row["type"] == "TOOL_REVIEW_OVERDUE"
            and row["entity_type"] == "tool"
            and row["entity_id"] == detail["id"]
            for row in findings
        ), "已过复核日期的工具没有进入治理待办"
    finally:
        db = SessionLocal()
        try:
            tool = db.query(Tool).filter(Tool.code == "VSM").one()
            tool.review_due_at = original
            db.commit()
        finally:
            db.close()
        client.post(f"{API}/baselines/audit-scan")


def test_tool_submission_review_and_direct_usage(client, manager_client, viewer_client):
    code = "E2E-" + uuid.uuid4().hex[:6].upper()
    payload = {
        "code": code,
        "name": "测试工具",
        "category": "DIAGNOSE",
        "stage_no": 1,
        "purpose": "验证工具提交审核与直接使用证据",
        "when_to_use": "只在测试中使用",
        "steps": ["第一步", "第二步"],
        "verification_standard": "能复现一次完整流程",
        "scenario_codes": ["FLOW"],
    }
    created = client.post(f"{API}/tools", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "DRAFT"

    public_codes = [row["code"] for row in client.get(f"{API}/tools").json()]
    assert code not in public_codes, "草稿工具不应出现在公开清单"

    denied = viewer_client.post(f"{API}/tools", json={**payload, "code": code + "X"})
    assert denied.status_code == 403

    submitted = client.post(f"{API}/tools/{code}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "IN_REVIEW"

    assert (
        viewer_client.post(f"{API}/tools/{code}/review", json={"decision": "APPROVE"}).status_code
        == 403
    )
    approved = manager_client.post(f"{API}/tools/{code}/review", json={"decision": "APPROVE"})
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "VERIFIED"
    assert approved.json()["last_verified_at"]

    public_codes = [row["code"] for row in client.get(f"{API}/tools").json()]
    assert code in public_codes, "审核通过的工具应出现在公开清单"

    usage_payload = {"step_no": "1.1", "outcome": "EFFECTIVE", "note": "测试使用"}
    first = client.post(f"{API}/tools/{code}/usage", json=usage_payload)
    second = client.post(f"{API}/tools/{code}/usage", json=usage_payload)
    assert first.status_code == 201, first.text
    assert second.json()["id"] == first.json()["id"], "工具使用证据没有短期去重"

    detail = client.get(f"{API}/tools/{code}").json()
    assert detail["usage"]["used"] == 1
    assert detail["usage_events"][0]["step_no"] == "1.1"

    archived = manager_client.post(f"{API}/tools/{code}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "ARCHIVED"
    assert code not in [row["code"] for row in client.get(f"{API}/tools").json()]
