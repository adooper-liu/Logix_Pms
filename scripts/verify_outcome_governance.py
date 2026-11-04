"""M8原页面办理：同轮原核验、培训操作、控制复盘与来源视图。"""

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_outcome_governance(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    pid = next(
        r["id"]
        for r in page.request.get(base + "/api/v1/execution/processes", headers=headers).json()
        if r["code"] == "L3-032"
    )
    page.evaluate(
        "id=>go('process_card',{params:{process:String(id),module:'governance'},skipOrigin:true})",
        pid,
    )
    expect(page.locator("#governanceEvidence")).to_contain_text("20项")
    page.locator('[data-act="governance.control"]').click()
    expect(page.locator("#gcEvidence")).to_be_visible()
    page.fill("#gcEvidence", "原绩效和异常周期回查")
    page.fill("#gcDecision", "维持原控制并复核")
    page.fill("#gcNext", "按期核对客户结果及绕行原因")
    page.fill("#gcDue", "2026-12-01")
    reviewer = next(
        r
        for r in page.request.get(base + "/api/v1/auth/users", headers=headers).json()
        if r["username"] == "manager"
    )
    page.select_option("#gcReviewer", str(reviewer["id"]))
    page.locator('[data-act="governance.saveControl"]').click()
    expect(page.locator("#governanceEvidence")).to_contain_text("维持原控制并复核")
    page.reload(wait_until="networkidle")
    expect(page.locator("#governanceEvidence")).to_contain_text("维持原控制并复核")
    print("OK   M8原流程卡20项来源、原PDCA控制复盘保存与刷新")
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    training = page.request.post(
        base + "/api/v1/pilot/training",
        headers=headers,
        data={
            "process_id": pid,
            "trainee_user_id": me["id"],
            "topic": "M8操作场景自检",
            "completed_on": "2026-11-04",
        },
    ).json()
    # 原模型先经现有读取入口登记基线，不假设种子已有版本行。
    model = page.request.get(base + f"/api/v1/processes/{pid}/design", headers=headers).json()
    frozen = page.request.post(
        base + f"/api/v1/processes/{pid}/design/freeze",
        headers=headers,
        data={"expected_version": model["version"], "note": "隔离自检固定操作输入"},
    )
    assert frozen.ok, frozen.text()
    page.reload(wait_until="networkidle")
    page.locator(f'[data-act="governance.operation"][data-id="{training["id"]}"]').click()
    page.fill("#goScenario", "正常办理及失败恢复")
    page.fill("#goEvidence", "原操作记录引用")
    page.fill("#goDue", "2026-12-01")
    page.select_option("#goReviewer", str(reviewer["id"]))
    with page.expect_response(
        lambda r: "/operation" in r.url and r.request.method == "PUT"
    ) as operation_response:
        page.locator('[data-act="governance.saveOperation"]').click()
    assert operation_response.value.ok, operation_response.value.text()
    expect(page.locator("#mask.show")).to_have_count(0)
    expect(page.locator("#governanceEvidence")).to_contain_text("操作待核验")
    project = page.request.post(
        base + "/api/v1/projects",
        headers=headers,
        data={"name": "M8复制准备", "methodology": "BPI", "owner": "测试", "process_id": pid},
    ).json()
    ctx = page.context.browser.new_context()
    try:
        p = ctx.new_page()
        p.goto(base, wait_until="networkidle")
        p.fill("#loginUser", "manager")
        p.fill("#loginPass", "manager123")
        p.click("#loginBtn")
        expect(p.locator("#loginMask")).not_to_be_visible()
        p.evaluate(
            "id=>go('process_card',{params:{process:String(id),module:'governance'},skipOrigin:true})",
            pid,
        )
        p.locator('[data-act="governance.review"]').last.click()
        p.fill("#gvEvidence", "本人核对原控制、客户结果与下次责任期限")
        p.locator('[data-act="governance.submitReview"]').click()
        expect(p.locator("#governanceEvidence")).to_contain_text("本人核对原控制")
        p.locator(f'[data-act="governance.operationReview"][data-id="{training["id"]}"]').click()
        p.fill("#gvEvidence", "本人观察正常操作与失败恢复")
        p.locator('[data-act="governance.submitReview"]').click()
        expect(p.locator("#governanceEvidence")).to_contain_text("原版本操作已核验")
    finally:
        ctx.close()
    page.evaluate("id=>go('projects',{params:{project:String(id)},skipOrigin:true})", project["id"])
    page.locator(f'[data-act="projects.replication"][data-id="{project["id"]}"]').click()
    expect(page.locator("#rpRound")).to_be_visible()
    expect(page.locator("#rpReceiver")).to_be_visible()
    page.evaluate("()=>closeModal()")
    # 原轮次原Gate用途入口：准备实际本流程原引用，非跳过场景。
    from uuid import uuid4

    kpi = page.request.post(
        base + "/api/v1/monitor/kpis",
        headers=headers,
        data={
            "code": "M8K-" + uuid4().hex[:8],
            "name": "M8核验前侧",
            "dimension": "EFFICIENCY",
            "process_id": pid,
            "unit": "小时",
            "formula": "原样本均值",
        },
    ).json()
    sample = page.request.post(
        base + f"/api/v1/monitor/kpis/{kpi['id']}/records",
        headers=headers,
        data={"period": "2026-10-01", "value": 2, "note": "人工前侧待核"},
    ).json()
    versions = page.request.get(
        base + f"/api/v1/processes/{pid}/design/versions", headers=headers
    ).json()
    created_round = page.request.post(
        base + f"/api/v1/processes/{pid}/improvement-rounds",
        headers=headers,
        data={
            "project_id": project["id"],
            "name": "M8核验入口",
            "scope_note": "本流程自检",
            "asis_model_version_id": versions[0]["id"],
            "baseline_window": {"start": "2026-10-01", "end": "2026-10-31"},
            "metrics": [
                {
                    "kpi_id": kpi["id"],
                    "source_semantics": "原均值",
                    "source_evidence": "原样本",
                    "calendar": "自然历时",
                }
            ],
            "baseline_samples": [
                {
                    "record_id": sample["id"],
                    "source_evidence": "原记录",
                    "quality_note": "待独立核实",
                }
            ],
        },
    )
    assert created_round.ok, created_round.text()
    rid = created_round.json()["id"]
    page.evaluate(
        "args=>go('process_card',{params:{process:String(args.pid),module:'rounds',round:String(args.rid)},skipOrigin:true})",
        {"pid": pid, "rid": rid},
    )
    page.locator('[data-act="round.outcome"]').click()
    expect(page.locator("#roPurpose")).to_be_visible()
    page.fill("#roEvidence", "缺事先约定必须拒绝")
    page.locator('[data-act="round.submitOutcome"]').click()
    expect(page.locator("#toast.err")).to_be_visible()
    expect(page.locator("#roEvidence")).to_have_value("缺事先约定必须拒绝")
    page.evaluate("()=>closeModal()")
    page.evaluate("()=>go('start',{skipOrigin:true})")
    page.request.delete(base + f"/api/v1/projects/{project['id']}", headers=headers)


def main():
    with isolated_app() as (base, folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            p = browser.new_page()
            p.goto(base, wait_until="networkidle")
            p.fill("#loginUser", "admin")
            p.fill("#loginPass", "admin123")
            p.click("#loginBtn")
            expect(p.locator("#loginMask")).not_to_be_visible()
            verify_outcome_governance(p, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
