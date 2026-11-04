"""M2实际入口、任务契约、原跳转及错误上下文。"""

from pathlib import Path

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_lifecycle(page, base):
    for module in ["core/router.js", "core/lifecycle.js", "views/start.js", "views/cbok.js"]:
        response = page.request.get(base + "/static/js/" + module)
        assert (
            response.ok
            and response.body()
            == (Path(__file__).resolve().parents[1] / "web/js" / module).read_bytes()
        ), "验证对象不是当前代码：" + module
    page.evaluate("() => go('start', {skipOrigin:true})")
    expect(page.locator('[data-act="lifecycle.process"]')).to_be_visible()
    assert page.locator('[data-act="lifecycle.open"][data-key]').count() == 9
    token = page.evaluate("localStorage.getItem('psm_token')")
    headers = {"Authorization": "Bearer " + token}
    rows = page.request.get(base + "/api/v1/process-map/flat?level=3", headers=headers).json()
    pid = next(row["id"] for row in rows if row["code"] == "L3-032")
    page.select_option('[data-act="lifecycle.process"]', str(pid))
    expect(page.locator("#view")).to_contain_text("L3-032")
    expected = [
        ("strategy", "strategy"),
        ("architecture", "pcf"),
        ("modeling", "designer"),
        ("analysis", "monitor"),
        ("design", "designer"),
        ("execution", "execution"),
        ("monitoring", "dashboard"),
        ("improvement", "projects"),
    ]
    requests = []

    def record(request):
        if request.method == "GET":
            requests.append(request.url)

    page.on("request", record)
    for key, view in expected:
        requests.clear()
        page.evaluate("pid => go('start', {params:{process:String(pid)}, skipOrigin:true})", pid)
        page.locator(f'[data-act="lifecycle.open"][data-key="{key}"]').click()
        expect(page.locator("#lifecycleTask")).to_contain_text("原产物")
        assert page.evaluate("state.view") == view
        assert page.evaluate("location.hash.includes('process=')")
        assert page.evaluate("key => location.hash.includes('lifecycle='+key)", key)
        for text in ["本步任务", "方法", "核验", "下一步"]:
            expect(page.locator("#lifecycleTask")).to_contain_text(text)
        if key in ("execution", "improvement"):
            prefix = "/api/v1/execution/tasks?" if key == "execution" else "/api/v1/projects?"
            assert any(prefix in url and "process_id=" + str(pid) in url for url in requests)
    page.remove_listener("request", record)
    page.locator('#lifecycleTask [data-act="lifecycle.method"]').first.click()
    expect(page.locator("#view .tb-detail-card")).to_be_visible()
    assert page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('process')") == str(
        pid
    )
    page.evaluate(
        "pid => go('designer', {params:{process:String(pid),lifecycle:'modeling',tab:'model'},skipOrigin:true})",
        pid,
    )
    expect(page.locator("#lifecycleTask")).to_contain_text("建模")
    page.reload(wait_until="networkidle")
    expect(page.locator("#lifecycleTask")).to_contain_text("建模")
    page.evaluate("pid => go('cbok', {params:{process:String(pid)},skipOrigin:true})", pid)
    expect(page.locator('[data-act="lifecycle.process"]')).to_have_value(str(pid))
    assert page.locator('[data-act="lifecycle.open"][data-key]').count() == 9
    page.locator('[data-act="lifecycle.open"][data-key="analysis"]').click()
    expect(page.locator("#lifecycleTask")).to_contain_text("分析")
    page.locator("#originBack").click()
    expect(page.locator('[data-act="lifecycle.process"]')).to_have_value(str(pid))
    page.evaluate(
        "() => go('designer', {params:{process:'99999999',lifecycle:'modeling'},skipOrigin:true})"
    )
    expect(page.locator("#view")).to_contain_text("流程不存在")
    assert page.locator("#bpmnCanvas").count() == 0
    page.evaluate("() => go('designer', {params:{lifecycle:'modeling'},skipOrigin:true})")
    expect(page.locator("#view")).to_contain_text("请先选择流程")
    assert page.locator("#bpmnCanvas").count() == 0
    page.evaluate("() => go('start', {skipOrigin:true})")
    page.wait_for_load_state("networkidle")
    # 请求返回较晚也不能覆盖同一view的新阶段。
    page.evaluate(
        """async (pid) => {
      const {renderAsync} = await import('/static/js/core/router.js');
      state.view = 'start';
      let release;
      const old = renderAsync('start', () => new Promise(resolve => { release = resolve; }), () => { document.getElementById('view').innerHTML = 'OLD-CONTEXT'; });
      await renderAsync('start', async () => null, () => { document.getElementById('view').innerHTML = 'NEW-CONTEXT'; });
      release(null); await old;
    }""",
        pid,
    )
    expect(page.locator("#view")).to_have_text("NEW-CONTEXT")
    page.evaluate("() => go('start', {skipOrigin:true})")
    page.wait_for_load_state("networkidle")
    print("OK   M2：共享八阶段任务、原跳转、流程上下文、刷新返回与非法引用拒绝")


def verify_lifecycle_handoffs(page, base):
    """原方法页、驾驶舱下钻和非法引用均不能丢失或偷用身份。"""
    token = page.evaluate("localStorage.getItem('psm_token')")
    headers = {"Authorization": "Bearer " + token}
    rows = page.request.get(base + "/api/v1/process-map/flat?level=3", headers=headers).json()
    pid = next(row["id"] for row in rows if row["code"] == "L3-032")
    created = page.request.post(
        base + "/api/v1/projects",
        headers=headers,
        data={"name": "M2承接自检", "methodology": "BPI", "owner": "流程管理科", "process_id": pid},
    )
    assert created.status == 201, created.text()
    project = created.json()["id"]
    try:
        page.evaluate(
            "args => go('start', {params:{process:String(args[0]),project:String(args[1])},skipOrigin:true})",
            [pid, project],
        )
        page.locator('[data-act="lifecycle.open"][data-key="strategy"]').click()
        expect(page.locator("#lifecycleTask")).to_contain_text("战略对齐")
        page.evaluate("() => { state.toolbox.step = '2.1'; }")
        page.locator('#lifecycleTask [data-act="lifecycle.method"]').first.click()
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        assert page.evaluate("state.toolbox.step") == "", "流程方法误用了上次项目的步骤"
        assert (
            page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('lifecycle')")
            == "strategy"
        ), "方法页丢失任务上下文"
        assert page.evaluate(
            "new URLSearchParams(location.hash.split('?')[1]).get('project')"
        ) == str(project), "方法页URL丢失项目，刷新后无法承接"
        page.reload(wait_until="networkidle")
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        assert page.evaluate(
            "new URLSearchParams(location.hash.split('?')[1]).get('project')"
        ) == str(project)

        page.evaluate(
            "pid => go('dashboard', {params:{process:String(pid),lifecycle:'monitoring'},skipOrigin:true})",
            pid,
        )
        expect(page.locator("#lifecycleTask")).to_contain_text("监控度量")
        page.locator('[data-act="cockpit.tab"][data-tab="kpi"]').click()
        expect(page.locator("#lifecycleTask")).to_contain_text("监控度量")
        page.reload(wait_until="networkidle")
        expect(page.locator("#lifecycleTask")).to_contain_text("监控度量")
        page.locator('#lifecycleTask [data-act="lifecycle.open"]').click()
        expect(page.locator("#lifecycleTask")).to_contain_text("变革优化")

        page.evaluate(
            "args => go('dashboard', {params:{process:String(args[0]),project:String(args[1]),lifecycle:'monitoring'},skipOrigin:true})",
            [pid, project],
        )
        expect(page.locator("#lifecycleTask")).to_contain_text("监控度量")
        page.locator('[data-act="cockpit.process"]').select_option("")
        page.wait_for_load_state("networkidle")
        assert (
            page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('process')") is None
        ), "全部流程仍恢复旧流程"
        assert (
            page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('project')") is None
        ), "全部流程仍关联旧项目"
        assert (
            page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('lifecycle')")
            is None
        ), "公司总览仍冒用单流程任务"
        expect(page.locator('[data-act="cockpit.process"]')).to_have_value("")
        assert page.locator("#lifecycleTask").count() == 0

        requests = []

        def record(request):
            if "/api/v1/" in request.url:
                requests.append(request.url)

        page.on("request", record)
        try:
            page.evaluate(
                "() => go('monitor', {params:{process:'99999999',lifecycle:'analysis',tab:'analysis'},skipOrigin:true})"
            )
            expect(page.locator("#view")).to_contain_text("流程不存在")
            page.wait_for_load_state("networkidle")
            assert not any(
                "/execution/mining?" in url or "/processes/99999999/" in url for url in requests
            ), "非法上下文仍执行了分析请求"
        finally:
            page.remove_listener("request", record)
        print("OK   M2补验：方法项目刷新、监控下钻/下一步、非法分析零业务请求")
    finally:
        page.request.delete(base + f"/api/v1/projects/{project}", headers=headers)
        page.evaluate("() => go('start', {skipOrigin:true})")
        page.wait_for_load_state("networkidle")


def verify_lifecycle_original_actions(page, base):
    """原页面入口和实际保存，不能绕过生命周期上下文。"""
    from uuid import uuid4

    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    rows = page.request.get(base + "/api/v1/process-map/flat?level=3", headers=headers).json()
    pid = next(row["id"] for row in rows if row["code"] == "L3-032")
    other = next(row["id"] for row in rows if row["id"] != pid)
    response = page.request.post(
        base + "/api/v1/projects",
        headers=headers,
        data={
            "name": "M2原入口-" + uuid4().hex[:8],
            "methodology": "BPI",
            "owner": "流程管理科",
            "process_id": pid,
        },
    )
    assert response.status == 201
    project = response.json()["id"]
    failed = []

    def scenario(name, action):
        try:
            action()
            print("OK   M2原操作：" + name)
        except AssertionError as error:
            failed.append(name + ": " + str(error).split("Aria snapshot:")[0][:200])
        finally:
            page.evaluate("() => closeModal()")

    def enter(view, key, process=pid, with_project=True):
        page.evaluate(
            "args => go(args.view,{params:{process:String(args.process),project:args.project?String(args.project):'',lifecycle:args.key},skipOrigin:true})",
            {
                "view": view,
                "key": key,
                "process": process,
                "project": project if with_project else None,
            },
        )
        expect(page.locator("#lifecycleTask")).to_be_visible()
        page.wait_for_timeout(500)
        page.wait_for_load_state("networkidle")

    def original_method():
        enter("strategy", "strategy")
        page.evaluate("() => {state.toolbox.step='2.1'}")
        page.locator('[data-act="toolmount.open"][data-code="SWOT"]').first.click()
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        assert page.evaluate(
            "new URLSearchParams(location.hash.split('?')[1]).get('process')"
        ) == str(pid), "原方法按钮丢流程"
        assert page.evaluate("state.toolbox.step") == "", "原方法按钮残留项目步骤"
        expect(page.locator("#lifecycleTask")).to_contain_text("战略对齐")

    def method_resources():
        enter("strategy", "strategy")
        page.locator('#lifecycleTask [data-act="lifecycle.method"]').first.click()
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        page.locator('[data-act="toolbox.clearSelected"]').first.click()
        page.wait_for_timeout(500)
        page.wait_for_load_state("networkidle")
        expect(page.locator("#lifecycleTask")).to_contain_text("战略对齐")
        assert "加载失败" not in page.inner_text("#view"), "返回匹配被上下文校验阻断"

    def alert_drilldown():
        for key in ["kpi_alert", "open_exceptions"]:
            enter("dashboard", "monitoring")
            page.locator(f'[data-act="dashboard.kpi"][data-key="{key}"]').click()
            expect(page.locator("#lifecycleTask")).to_contain_text("监控度量")
            assert page.evaluate(
                "new URLSearchParams(location.hash.split('?')[1]).get('project')"
            ) == str(project)

    def sheet_after_process_switch():
        enter("designer", "modeling")
        page.locator('[data-act="designer.process"]').select_option(str(other))
        expect(page.locator("#lifecycleTask")).to_contain_text(
            next(row["code"] for row in rows if row["id"] == other)
        )
        page.wait_for_load_state("networkidle")
        assert (
            page.evaluate("new URLSearchParams(location.hash.split('?')[1]).get('project')") is None
        ), "换流程没有清理URL项目"
        page.evaluate(
            "args => state.navTrail.push({view:'projects',params:{project:String(args.project),process:String(args.pid)}})",
            {"project": project, "pid": pid},
        )
        page.locator('#lifecycleTask [data-act="lifecycle.method"][data-code="BPMN"]').click()
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        page.locator('[data-act="toolbox.fillSheet"][data-code="BPMN"]').first.click()
        expect(page.locator("#tsProcess")).to_have_value(str(other))
        form = page.request.get(base + "/api/v1/tools/BPMN/sheet-form", headers=headers).json()
        for field in form["fields"]:
            element = page.locator("#ts-" + field["key"])
            if field["kind"] == "choice" and field["options"]:
                element.select_option(field["options"][0])
            else:
                element.fill("M2上下文-" + uuid4().hex[:8])
        with page.expect_response(
            lambda response: (
                response.request.method == "POST" and response.url.endswith("/tools/BPMN/sheets")
            )
        ) as saved:
            page.locator('#mFoot [data-act="toolbox.submitSheet"]').click()
        assert saved.value.status == 201, saved.value.text()
        assert saved.value.json()["project_id"] is None, "换流程后从来源栈误取旧项目"

    def delayed_designer():
        path = f"**/api/v1/processes/{pid}/design"
        pending = []
        page.route(path, lambda route: pending.append(route))
        try:
            enter("strategy", "strategy", with_project=False)
            page.evaluate(
                "pid => go('designer',{params:{process:String(pid),lifecycle:'modeling'},skipOrigin:true})",
                pid,
            )
            for _ in range(100):
                if pending:
                    break
                page.wait_for_timeout(50)
            assert pending, "没有捕获延迟模型请求"
            page.evaluate(
                "pid => go('designer',{params:{process:String(pid),lifecycle:'modeling'},skipOrigin:true})",
                other,
            )
            expect(page.locator("#lifecycleTask")).to_contain_text(
                next(row["code"] for row in rows if row["id"] == other)
            )
            assert page.evaluate("state.designer.model.process_id") == other
            pending[0].continue_()
            page.wait_for_timeout(1000)
            page.wait_for_load_state("networkidle")
            assert page.evaluate("state.designer.model.process_id") == other, (
                "旧请求改写新流程共享模型"
            )
            assert page.evaluate("state.designer.savedModel.process_id") == other
        finally:
            for route in pending[1:]:
                route.continue_()
            page.unroute(path)

    try:
        scenario("原方法按钮", original_method)
        scenario("方法返回资源列表", method_resources)
        scenario("原告警下钻", alert_drilldown)
        scenario("换流程后的方法产物归属", sheet_after_process_switch)
        scenario("旧设计请求不能改写共享模型", delayed_designer)
        assert not failed, "\n".join(failed)
    finally:
        page.request.delete(base + f"/api/v1/projects/{project}", headers=headers)
        page.evaluate("() => go('start',{skipOrigin:true})")
        page.wait_for_load_state("networkidle")


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
            verify_lifecycle(page, base)
            verify_lifecycle_handoffs(page, base)
            verify_lifecycle_original_actions(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
