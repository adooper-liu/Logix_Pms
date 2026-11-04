"""M7原指标和原异常办理真实浏览器验证。"""

from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_monitor_decision_loop(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    pid = next(
        p["id"]
        for p in page.request.get(base + "/api/v1/execution/processes", headers=headers).json()
        if p["code"] == "L3-032"
    )
    result = page.request.post(
        base + "/api/v1/monitor/kpis",
        headers=headers,
        data={
            "code": "M7UI-" + uuid4().hex[:8],
            "name": "M7测量自检",
            "dimension": "EFFICIENCY",
            "unit": "小时",
            "process_id": pid,
            "formula": "端到端月均历时",
        },
    )
    assert result.ok, result.text()
    kid = result.json()["id"]
    page.evaluate("()=>go('monitor',{params:{tab:'kpi'},skipOrigin:true})")
    page.locator(f'[data-act="monitor.editKpi"][data-id="{kid}"]').click()
    expect(page.locator("#nkMeasureSource")).to_be_visible()
    page.select_option("#nkMeasureSource", "EXECUTION_ELAPSED")
    page.fill("#nkPurpose", "核对客户周期")
    page.fill("#nkResponse", "数据责任人核实后处置")
    page.locator('[data-act="monitor.submitKpi"]').click()
    expect(page.locator("#toast")).to_contain_text("已更新")
    current = page.request.get(base + f"/api/v1/monitor/kpis/{kid}", headers=headers).json()
    assert current["measurement"]["source_kind"] == "EXECUTION_ELAPSED"
    assert current["status"] == "GRAY"
    print("OK   M7原指标显式取数保存、缺正式样本不判绿")
    # 保存实际API成功后延迟响应，不得关闭新开的输入表单。
    page.locator(f'[data-act="monitor.editKpi"][data-id="{kid}"]').click()
    expect(page.locator("#nkName")).to_be_visible()

    def late_save(route):
        response = route.fetch()
        page.evaluate(
            "()=>{closeModal();const b=document.createElement('button');b.dataset.act='monitor.newKpi';document.body.append(b);b.click();b.remove();document.getElementById('nkName').value='新表单未保存';}"
        )
        route.fulfill(response=response)

    page.route(
        "**/api/v1/monitor/kpis/" + str(kid),
        lambda r: late_save(r) if r.request.method == "PATCH" else r.continue_(),
    )
    with page.expect_response(
        lambda r: r.request.method == "PATCH" and "/monitor/kpis/" + str(kid) in r.url
    ):
        page.locator('[data-act="monitor.submitKpi"]').click()
    page.wait_for_timeout(200)
    expect(page.locator("#toast")).to_contain_text("已更新")
    expect(page.locator("#nkName")).to_be_visible()
    expect(page.locator("#nkName")).to_have_value("新表单未保存")
    page.unroute("**/api/v1/monitor/kpis/" + str(kid))
    page.evaluate("()=>closeModal()")
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    event = page.request.post(
        base + "/api/v1/monitor/exceptions",
        headers=headers,
        data={"title": "M7异常办理自检", "owner_user_id": me["id"]},
    ).json()
    page.evaluate("()=>go('monitor',{params:{tab:'exceptions'},skipOrigin:true})")
    page.locator(f'[data-act="monitor.openException"][data-id="{event["id"]}"]').click()
    page.locator("#mBody details summary").click()
    expect(page.locator("#exActionRef")).to_be_visible()
    page.fill("#exAction", "调整原表单并验证")
    page.select_option("#exStatus", "RESOLVED")
    reviewer = next(
        u
        for u in page.request.get(base + "/api/v1/auth/users", headers=headers).json()
        if u["username"] == "chen"
    )
    page.select_option("#exReviewer", str(reviewer["id"]))
    page.fill("#exDecision", "采用原处置方案")
    page.fill("#exActionRef", "原表单修改记录")
    page.fill("#exEvidence", "原执行依据")
    page.fill("#exExpected", "同类异常不复发")
    page.fill("#exReviewDue", "2026-12-01")
    page.locator('[data-act="monitor.saveException"]').click()
    expect(page.locator("#toast")).to_contain_text("已更新")
    ctx = page.context.browser.new_context()
    try:
        p = ctx.new_page()
        p.goto(base, wait_until="networkidle")
        p.fill("#loginUser", "chen")
        p.fill("#loginPass", "chen123")
        p.click("#loginBtn")
        expect(p.locator("#loginMask")).not_to_be_visible()
        p.evaluate("()=>go('monitor',{params:{tab:'exceptions'},skipOrigin:true})")
        p.locator(f'[data-act="monitor.openException"][data-id="{event["id"]}"]').click()
        p.fill("#exReviewEvidence", "本人回查执行原记录")
        p.fill("#exReviewResult", "预期结果已核实")
        p.locator('[data-act="monitor.reviewException"]:not([data-decision])').click()
        expect(p.locator("#toast")).to_contain_text("核验已记录")
    finally:
        ctx.close()
    updated = page.request.get(
        base + f"/api/v1/monitor/exceptions/{event['id']}", headers=headers
    ).json()
    assert updated["status"] == "CLOSED"
    page.request.delete(base + f"/api/v1/monitor/exceptions/{event['id']}", headers=headers)
    print("OK   M7原异常处置、指定本人UI核验与关闭")
    # 实际API响应仅延迟交付，验证加载开始时的流程身份。
    event = page.request.post(
        base + "/api/v1/monitor/exceptions",
        headers=headers,
        data={"title": "M7延迟上下文", "owner_user_id": me["id"]},
    ).json()
    try:

        def delayed(route):
            response = route.fetch()
            page.evaluate("()=>{state.cockpit.processId=999999;}")
            route.fulfill(response=response)

        page.route("**/api/v1/monitor/exceptions/" + str(event["id"]), delayed)
        page.evaluate(
            "pid=>{state.cockpit.processId=pid;const b=document.createElement('button');b.id='m7DelayOpen';b.dataset.act='monitor.openException';b.dataset.id='"
            + str(event["id"])
            + "';document.body.append(b);b.click();b.remove();}",
            pid,
        )
        expect(page.locator("#mask")).not_to_have_class("mask show")
        expect(page.locator("#exAction")).to_have_count(0)
        page.unroute("**/api/v1/monitor/exceptions/" + str(event["id"]), delayed)
    finally:
        page.evaluate("()=>closeModal()")
        page.request.delete(base + f"/api/v1/monitor/exceptions/{event['id']}", headers=headers)


def main():
    with isolated_app() as (base, folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(base, wait_until="networkidle")
            page.fill("#loginUser", "admin")
            page.fill("#loginPass", "admin123")
            page.click("#loginBtn")
            expect(page.locator("#loginMask")).not_to_be_visible()
            verify_monitor_decision_loop(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
