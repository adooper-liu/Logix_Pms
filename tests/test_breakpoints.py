"""断点：KPI 正式来源、办理授权、异常待确认。"""

from app.core.database import SessionLocal
from app.models.monitor import ExceptionEvent

API = "/api/v1"


def _process_id(client, code: str) -> int:
    rows = client.get(f"{API}/execution/processes").json()
    return next(row["id"] for row in rows if row["code"] == code)


def test_duration_kpi_comes_from_execution(client):
    process_id = _process_id(client, "L3-032")
    created = client.post(
        f"{API}/monitor/kpis",
        json={
            "code": "KPI-SRC-TIME",
            "name": "来源测试周期",
            "dimension": "EFFICIENCY",
            "direction": "LOWER_BETTER",
            "unit": "天",
            "formula": "完成时间减开始时间",
            "process_id": process_id,
            "target_value": 3,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["intake"] == "DRAFT"
    assert body["intake_label"] == "未定来源"


def test_rate_kpi_without_hook_is_not_official(client):
    before = client.get(f"{API}/dashboard/home").json()["kpi_red_yellow"]
    created = client.post(
        f"{API}/monitor/kpis",
        json={
            "code": "KPI-SRC-RATE",
            "name": "来源测试达成率",
            "dimension": "QUALITY",
            "direction": "HIGHER_BETTER",
            "unit": "%",
            "formula": "达成数除以应达成数",
            "target_value": 95,
        },
    )
    assert created.status_code == 201, created.text
    kpi = created.json()
    assert kpi["intake"] == "DRAFT"
    assert kpi["status_label"] == "未定来源"
    assert kpi["achievement_rate"] is None

    recorded = client.post(
        f"{API}/monitor/kpis/{kpi['id']}/records",
        json={"period": "2026-09-01", "value": 10},
    )
    assert recorded.status_code == 201, recorded.text
    again = client.get(f"{API}/monitor/kpis/{kpi['id']}").json()
    assert again["status"] == "GRAY"
    assert again["achievement_rate"] is None

    radar = client.get(f"{API}/monitor/kpi-radar").json()
    series = next(row for row in radar["series"] if row["code"] == "KPI-SRC-RATE")
    assert series["intake"] == "DRAFT"
    assert series["status_label"] == "未定来源"

    candidates = client.get(f"{API}/monitor/improvement-candidates").json()
    assert all(row["code"] != "KPI-SRC-RATE" for row in candidates)
    after = client.get(f"{API}/dashboard/home").json()["kpi_red_yellow"]
    assert after == before


def test_rate_kpi_with_hook_is_inbound(client):
    me = client.get(f"{API}/auth/me").json()
    hook = client.post(
        f"{API}/integrations/inbound-hooks",
        json={
            "code": "HOOK-SRC-1",
            "name": "达成率回传",
            "actions": ["record_kpi"],
            "run_as_user_id": me["id"],
        },
    )
    assert hook.status_code == 201, hook.text
    created = client.post(
        f"{API}/monitor/kpis",
        json={
            "code": "KPI-SRC-IN",
            "name": "钩子达成率",
            "dimension": "QUALITY",
            "direction": "HIGHER_BETTER",
            "unit": "%",
            "formula": "回传达成数除以应达成数",
            "inbound_webhook_id": hook.json()["id"],
            "target_value": 95,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["intake"] == "INBOUND"
    assert created.json()["intake_label"] == "入站回传"


def test_task_complete_requires_approver_or_exception(client):
    process_id = _process_id(client, "L3-032")
    started = client.post(
        f"{API}/execution/instances",
        json={"process_id": process_id, "variables": {"case": "auth-gate"}},
    )
    assert started.status_code == 201, started.text
    instance_id = started.json()["id"]
    tasks = client.get(
        f"{API}/execution/tasks",
        params={"instance_id": instance_id, "only_open": True},
    ).json()
    task = tasks[0]
    roles = client.get(f"{API}/governance/roles").json()
    approver = next(row["id"] for row in roles if row["code"] == "GR-002")
    rule = client.post(
        f"{API}/authorization/rules",
        json={
            "title": "办理人必须是审批角色",
            "matter": task["name"],
            "category": "B",
            "process_id": process_id,
            "approver_role_id": approver,
            "amount_limit": 99999999,
            "exception_path": "由审批角色批准例外",
            "evidence_required": "例外申请",
        },
    )
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["id"]
    rule_code = rule.json()["code"]
    try:
        assert client.post(f"{API}/authorization/rules/{rule_id}/activate").status_code == 200
        blocked = client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={"form_data": {"applicant": "张三", "amount": 1000, "description": "授权测试"}},
        )
        assert blocked.status_code == 403
        assert rule_code in blocked.json()["detail"]

        exc = client.post(
            f"{API}/authorization/exceptions",
            json={
                "rule_id": rule_id,
                "title": "本次放行",
                "reason": "测试已批准例外",
                "process_id": process_id,
                "expires_at": "2027-12-31T00:00:00",
            },
        )
        assert exc.status_code == 201, exc.text
        approved = client.post(
            f"{API}/authorization/exceptions/{exc.json()['id']}/approve",
            json={"note": "同意"},
        )
        assert approved.status_code == 200, approved.text
        allowed = client.post(
            f"{API}/execution/tasks/{task['id']}/complete",
            json={"form_data": {"applicant": "张三", "amount": 1000, "description": "授权测试"}},
        )
        assert allowed.status_code == 200, allowed.text
    finally:
        client.post(f"{API}/authorization/rules/{rule_id}/retire")
        client.post(f"{API}/execution/instances/{instance_id}/cancel")
        client.delete(f"{API}/execution/instances/{instance_id}")


def test_exception_suggestion_inserts_only_after_confirm(client):
    before = client.get(f"{API}/monitor/exceptions/summary").json()["total"]
    listed = client.get(f"{API}/monitor/exception-suggestions").json()
    assert client.get(f"{API}/monitor/exceptions/summary").json()["total"] == before
    assert isinstance(listed, list)

    kpis = client.get(f"{API}/monitor/kpis").json()
    source_id = next(row["id"] for row in kpis if row["code"] == "KPI-SRC-TIME")
    first = client.post(
        f"{API}/monitor/exceptions",
        json={
            "title": "来源测试异常",
            "severity": "HIGH",
            "source_kpi_id": source_id,
            "process_id": next(row["process_id"] for row in kpis if row["id"] == source_id),
        },
    )
    assert first.status_code == 201, first.text
    assert first.json()["source_kpi_id"] == source_id
    second = client.post(
        f"{API}/monitor/exceptions",
        json={
            "title": "来源测试异常再次",
            "severity": "HIGH",
            "source_kpi_id": source_id,
            "process_id": next(row["process_id"] for row in kpis if row["id"] == source_id),
        },
    )
    assert second.status_code == 409

    db = SessionLocal()
    try:
        db.query(ExceptionEvent).filter(ExceptionEvent.id == first.json()["id"]).delete()
        db.commit()
    finally:
        db.close()
