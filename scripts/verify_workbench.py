"""M4同一原画布/分析页的作业办理，不经工具跳转替代。"""

from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_workbench(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    people = page.request.get(base + "/api/v1/auth/users", headers=headers).json()
    reviewer = next(row for row in people if row["username"] == "chen")
    proc = page.request.post(
        base + "/api/v1/process-map",
        headers=headers,
        data={
            "code": "M4-UI-" + uuid4().hex[:8],
            "name": "M4作业自检",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()
    pid = proc["id"]
    try:
        response = page.request.put(
            base + f"/api/v1/processes/{pid}/design",
            headers=headers,
            data={
                "nodes": [
                    {"node_key": "s", "name": "开始", "node_type": "START"},
                    {"node_key": "a", "name": "核对", "node_type": "TASK"},
                    {"node_key": "e", "name": "结束", "node_type": "END"},
                ],
                "edges": [
                    {"source_key": "s", "target_key": "a"},
                    {"source_key": "a", "target_key": "e"},
                ],
            },
        )
        assert response.ok, response.text()
        page.evaluate(
            "pid=>go('designer',{params:{process:String(pid),lifecycle:'modeling'},skipOrigin:true})",
            pid,
        )
        expect(page.locator("#workbench")).to_contain_text("现状建模")
        page.locator('[data-act="work.freeze"]').click()
        expect(page.locator("#workbench")).to_contain_text("已固定")
        upstream = None
        for kind, view, key in [
            ("MODELING", "designer", "modeling"),
            ("ANALYSIS", "monitor", "analysis"),
            ("DESIGN", "designer", "design"),
        ]:
            page.evaluate(
                "args=>go(args.view,{params:{process:String(args.pid),lifecycle:args.key,tab:args.view==='monitor'?'analysis':'model'},skipOrigin:true})",
                {"pid": pid, "view": view, "key": key},
            )
            expect(page.locator("#workbench")).to_contain_text(
                {"MODELING": "现状建模", "ANALYSIS": "分析交付", "DESIGN": "方案设计"}[kind]
            )
            page.locator('[data-act="work.new"]').click()
            expect(page.locator("#wrCustomer")).to_be_visible()
            page.select_option("#wrSource", "OBSERVED")
            page.select_option("#wrReviewer", str(reviewer["id"]))
            if upstream:
                page.select_option("#wrUpstream", str(upstream))
            for field in [
                "Customer",
                "Problem",
                "Findings",
                "Evidence",
                "Limitations",
                "Next",
                "Alternatives",
                "Choice",
                "Controls",
                "Validation",
                "Rollback",
            ]:
                element = page.locator("#wr" + field)
                if element.count():
                    element.fill("M4作业-" + field)
            with page.expect_response(
                lambda r: r.request.method == "POST" and r.url.endswith("/work-records")
            ) as saved:
                page.locator('[data-act="work.save"]').click()
            assert saved.value.status == 201, saved.value.text()
            row = saved.value.json()
            upstream = row["id"]
            expect(page.locator("#workbench")).to_contain_text("待指定接收者核验")
            # 专项以真实指定账号API决定；UI写入/列表走真实页面，不冒称已登录第二用户UI。
            login = page.request.post(
                base + "/api/v1/auth/login", data={"username": "chen", "password": "chen123"}
            ).json()
            accepted = page.request.post(
                base + f"/api/v1/processes/{pid}/work-records/{upstream}/review",
                headers={"Authorization": "Bearer " + login["token"]},
                data={
                    "decision": "ACCEPT",
                    "evidence": "指定本人核对原模型与该版产物",
                    "expected_revision": 0,
                },
            )
            assert accepted.status == 200, accepted.text()
            page.reload(wait_until="networkidle")
            expect(page.locator("#workbench")).to_contain_text("本用途已接收")
        assert (
            page.request.get(base + f"/api/v1/processes/{pid}/design", headers=headers).json()[
                "published_version"
            ]
            == 0
        )
        print("OK   M4：原画布建模/设计、分析页直接作业、固定不发布、无项目交付与本人核验API")
    finally:
        page.evaluate("()=>go('start',{skipOrigin:true})")
        page.wait_for_load_state("networkidle")
        page.request.delete(base + f"/api/v1/process-map/{pid}", headers=headers)


def verify_workbench_guards(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    proc = page.request.post(
        base + "/api/v1/process-map",
        headers=headers,
        data={
            "code": "M4-G-" + uuid4().hex[:8],
            "name": "M4上下文守卫",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()
    pid = proc["id"]
    project = None
    try:
        model = page.request.put(
            base + f"/api/v1/processes/{pid}/design",
            headers=headers,
            data={"nodes": [{"node_key": "a", "name": "活动", "node_type": "TASK"}], "edges": []},
        ).json()
        page.request.post(
            base + f"/api/v1/processes/{pid}/design/freeze",
            headers=headers,
            data={"expected_version": model["version"], "note": "守卫输入"},
        )
        project = page.request.post(
            base + "/api/v1/projects",
            headers=headers,
            data={
                "name": "M4上下文项目",
                "methodology": "BPI",
                "owner": "流程管理科",
                "process_id": pid,
            },
        ).json()["id"]
        page.evaluate(
            "args=>go('designer',{params:{process:String(args[0]),project:String(args[1]),lifecycle:'modeling'},skipOrigin:true})",
            [pid, project],
        )
        expect(page.locator("#workbench")).to_be_visible()
        page.locator('[data-act="work.new"]').click()
        page.fill("#wrCustomer", "客户")
        page.fill("#wrProblem", "上下文不得丢失")
        page.select_option("#wrReviewer", index=1)
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/work-records")
        ) as saved:
            page.locator('[data-act="work.save"]').click()
        assert saved.value.status == 201, saved.value.text()
        assert saved.value.json()["project_id"] == project, "原页面丢失显式项目身份"
        page.wait_for_load_state("networkidle")
        # 旧普通设计器允许草稿流程，只限制新增业务作业。
        page.request.patch(base + f"/api/v1/process-map/{pid}", headers=headers, data={})
        page.evaluate("pid=>go('designer',{params:{process:String(pid)},skipOrigin:true})", pid)
        page.wait_for_load_state("networkidle")
        page.locator('[data-act="work.mode"]').click()
        page.wait_for_load_state("networkidle")
        page.evaluate(
            "pid=>go('designer',{params:{process:String(pid),lifecycle:'modeling'},skipOrigin:true})",
            pid,
        )
        expect(page.locator("#workbench h3")).to_contain_text("现状建模")
        print("OK   M4守卫：显式项目保留、建模任务覆盖普通用途缓存")
    finally:
        page.evaluate("()=>go('start',{skipOrigin:true})")
        page.wait_for_load_state("networkidle")
        if project:
            page.request.delete(base + f"/api/v1/projects/{project}", headers=headers)
        page.request.delete(base + f"/api/v1/process-map/{pid}", headers=headers)


def verify_work_review_guards(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    reviewer = next(
        row
        for row in page.request.get(base + "/api/v1/auth/users", headers=headers).json()
        if row["username"] == "chen"
    )
    proc = page.request.post(
        base + "/api/v1/process-map",
        headers=headers,
        data={
            "code": "M4-R-" + uuid4().hex[:8],
            "name": "M4核验守卫",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()
    pid = proc["id"]
    second = None
    try:
        model = page.request.put(
            base + f"/api/v1/processes/{pid}/design",
            headers=headers,
            data={"nodes": [{"node_key": "a", "name": "活动", "node_type": "TASK"}], "edges": []},
        ).json()
        frozen = page.request.post(
            base + f"/api/v1/processes/{pid}/design/freeze",
            headers=headers,
            data={"expected_version": model["version"], "note": "输入"},
        ).json()
        record = page.request.post(
            base + f"/api/v1/processes/{pid}/work-records",
            headers=headers,
            data={
                "kind": "MODELING",
                "model_version_id": frozen["id"],
                "source_kind": "OBSERVED",
                "reviewer_user_id": reviewer["id"],
                "customer_result": "客户结果",
                "problem": "核验守卫",
                "findings": "现场",
                "evidence": "原样本",
                "limitations": "限定范围",
                "next_action": "交给分析",
            },
        ).json()
        # 独立浏览器context登录实际核验账号，不覆盖主页面admin身份。
        context = page.context.browser.new_context()
        second = context.new_page()
        second.goto(base, wait_until="networkidle")
        second.fill("#loginUser", "chen")
        second.fill("#loginPass", "chen123")
        second.click("#loginBtn")
        expect(second.locator("#loginMask")).not_to_be_visible()

        def enter():
            second.evaluate(
                "pid=>go('monitor',{params:{process:String(pid),tab:'analysis'},skipOrigin:true})",
                pid,
            )
            expect(second.locator("#workbench")).to_be_visible()
            second.locator("#workbench summary").click()
            second.locator(f'[data-act="work.review"][data-id="{record["id"]}"]').click()
            expect(second.locator("#wvEvidence")).to_be_visible()

        enter()
        second.fill("#wvEvidence", "旧流程不可写入")
        requests = []
        second.on(
            "request",
            lambda request: (
                requests.append(request.url)
                if request.method == "POST" and request.url.endswith("/review")
                else None
            ),
        )
        second.evaluate("()=>go('start',{skipOrigin:true})")
        second.wait_for_load_state("networkidle")
        second.locator('[data-act="work.submitReview"]').click()
        second.wait_for_timeout(400)
        assert not requests, "切流程后旧核验弹窗仍提交"
        second.evaluate("()=>closeModal()")
        enter()
        second.fill("#wvEvidence", "本人核验")
        pending = []
        pattern = "**/work-records/*/review"
        second.route(pattern, lambda route: pending.append(route))
        second.locator('[data-act="work.submitReview"]').click()
        for _ in range(50):
            if pending:
                break
            second.wait_for_timeout(50)
        assert pending
        second.evaluate(
            "async()=>{const ui=await import('/static/js/core/ui.js');ui.closeModal();ui.openModal('新表单','<input id=guardNewInput value=保留输入>');}"
        )
        pending[0].continue_()
        second.wait_for_timeout(700)
        expect(second.locator("#guardNewInput")).to_have_value("保留输入")
        second.unroute(pattern)
        print("OK   M4核验守卫：实际核验账号、切流程拒绝旧提交、晚响应保留新表单")
    finally:
        second.close()
        if "context" in locals():
            context.close()
        page.request.delete(base + f"/api/v1/process-map/{pid}", headers=headers)


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
            verify_workbench(page, base)
            verify_workbench_guards(page, base)
            verify_work_review_guards(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
