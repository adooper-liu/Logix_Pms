"""M6原执行页上线准备与无RPA范围核对。"""

from uuid import uuid4

from binding_gate_fixture import add_bindings, api_for
from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_execution_readiness(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    reviewer = next(
        row
        for row in page.request.get(base + "/api/v1/auth/users", headers=headers).json()
        if row["username"] == "chen"
    )
    pid = page.request.post(
        base + "/api/v1/process-map",
        headers=headers,
        data={
            "code": "M6UI-" + uuid4().hex[:8],
            "name": "M6准备自检",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()["id"]
    api, _headers = api_for(page, base)
    suffix = uuid4().hex[:8]
    activity = api(
        "POST",
        "/process-map",
        {"code": "M6A-" + suffix, "name": "上线合成活动", "level": 4, "parent_id": pid},
    )
    position = api("POST", "/positions", {"code": "M6P-" + suffix, "name": "上线合成岗位"})
    try:
        page.request.put(
            base + f"/api/v1/processes/{pid}/design",
            headers=headers,
            data={
                "nodes": [
                    {
                        "node_key": "a",
                        "name": "办理",
                        "node_type": "TASK",
                        "process_arch_id": activity["id"],
                        "owner_position_id": position["id"],
                    }
                ],
                "edges": [],
            },
        )
        add_bindings(page, base, pid, activity["id"], position["id"], "a", performance=False)
        page.request.post(
            base + f"/api/v1/processes/{pid}/design/submit-review",
            headers=headers,
            data={"note": "评审"},
        )
        published = page.request.post(
            base + f"/api/v1/processes/{pid}/design/publish",
            headers=headers,
            data={
                "change_note": "上线准备自检发布",
                "self_publish_reason": "隔离测试核对运行原身份",
            },
        )
        assert published.ok, published.text()
        page.evaluate(
            "pid=>go('execution',{params:{process:String(pid),tab:'config'},skipOrigin:true})", pid
        )
        expect(page.locator("#executionReadiness")).to_contain_text("上线准备")
        page.locator('[data-act="ready.edit"]').click()
        expect(page.locator("#erReviewer")).to_be_visible()
        page.select_option("#erReviewer", str(reviewer["id"]))
        for key in ["forms", "assignments", "deadlines"]:
            page.select_option("#erMode-" + key, "NOT_APPLICABLE")
            page.fill("#erReason-" + key, "本范围人工办理，无此项要求；原控制另核")
        page.select_option("#erMode-forms", "REQUIRED")
        page.locator("#mBody details summary").click()
        page.select_option("#erNodeMode-0-forms", "NOT_APPLICABLE")
        page.fill("#erNodeReason-0-forms", "本任务不收结构化字段，其他任务继承默认")
        page.fill("#erEvidence", "场景、权限、失败与恢复已按原资料核对")
        page.fill("#erRollback", "停止新实例并回到原发布版，旧实例沿原快照")
        # 错误应保留表单；再修正提交，不能把失败当成功关闭。
        page.fill("#erRollback", "")
        page.locator('[data-act="ready.save"]').click()
        expect(page.locator("#toast.err.show")).to_be_visible()
        expect(page.locator("#erEvidence")).to_have_value("场景、权限、失败与恢复已按原资料核对")
        page.fill("#erRollback", "停止新实例并回到原发布版，旧实例沿原快照")
        page.locator('[data-act="ready.save"]').click()
        expect(page.locator("#executionReadiness")).to_contain_text("待本人确认")
        page.reload(wait_until="networkidle")
        expect(page.locator("#executionReadiness")).to_contain_text("待本人确认")
        reviewer_context = page.context.browser.new_context()
        try:
            reviewer_page = reviewer_context.new_page()
            reviewer_page.goto(base, wait_until="networkidle")
            reviewer_page.fill("#loginUser", "chen")
            reviewer_page.fill("#loginPass", "chen123")
            reviewer_page.click("#loginBtn")
            expect(reviewer_page.locator("#loginMask")).not_to_be_visible()
            reviewer_page.evaluate(
                "pid=>go('execution',{params:{process:String(pid),tab:'config'},skipOrigin:true})",
                pid,
            )
            reviewer_page.locator('[data-act="ready.confirm"]').click()
            reviewer_page.fill("#erDecisionEvidence", "指定本人核对原发布与准备适用性")
            reviewer_page.locator('[data-act="ready.submitConfirm"]').click()
            expect(reviewer_page.locator("#executionReadiness")).to_contain_text("已确认")
        finally:
            reviewer_context.close()
        page.reload(wait_until="networkidle")
        expect(page.locator("#executionReadiness")).to_contain_text("已确认")
        page.request.put(
            base + f"/api/v1/execution/config?process_id={pid}",
            headers=headers,
            data={"default_task_due_hours": 2},
        )
        page.reload(wait_until="networkidle")
        expect(page.locator("#executionReadiness")).to_contain_text("待复核")
        page.locator('[data-act="ready.edit"]').click()
        expect(page.locator("#erEvidence")).to_be_visible()
        writes = []

        def track_write(request):
            if "/execution/readiness" in request.url and request.method in ("PUT", "POST"):
                writes.append(request.url)

        page.on("request", track_write)
        other = next(
            row
            for row in page.request.get(
                base + "/api/v1/execution/processes", headers=headers
            ).json()
            if row["id"] != pid
        )
        page.evaluate(
            "id=>go('execution',{params:{process:String(id),tab:'config'},skipOrigin:true})",
            other["id"],
        )
        expect(page.locator("#exConfigProcess")).to_have_value(str(other["id"]))
        page.locator('[data-act="ready.save"]').click()
        expect(page.locator("#toast")).to_contain_text("流程上下文已变化")
        assert not writes, writes
        page.remove_listener("request", track_write)
        page.locator('#mFoot [data-act="ui.close"]').click()
        print(
            "OK   M6：原执行页准备、错误输入保留、刷新、指定本人UI确认、配置变化待复核、切流程零旧提交"
        )
        path = page.request.post(
            base + "/api/v1/pilot/paths", headers=headers, data={"process_id": pid}
        ).json()
        page.evaluate(
            "id=>go('pilot',{params:{path:String(id),layer:'6'},skipOrigin:true})", path["id"]
        )
        page.locator('[data-act="pilot.editApplicability"]').click()
        page.select_option("#paMode-rpa_bots", "REQUIRED")
        page.fill("#paReason-rpa_bots", "本范围明确采用机器人，需回查原证据")
        page.locator('[data-act="pilot.saveApplicability"]').click()
        expect(page.locator("#view")).to_contain_text("本范围明确采用机器人")
        page.locator('[data-act="pilot.editApplicability"]').click()
        with page.expect_response(
            lambda r: "/api/v1/pilot/paths" in r.url and r.request.method == "GET"
        ):
            page.evaluate(
                "id=>go('pilot',{params:{path:String(id),layer:'6'},skipOrigin:true})", path["id"]
            )
        # 复现真实请求在途边界：改变选中路径但旧详情尚未返回。
        page.evaluate("()=>{state.pilot.pathId=999999;}")
        before = page.request.get(
            base + f"/api/v1/pilot/paths/{path['id']}", headers=headers
        ).json()["layers"][5]["applicability_revision"]
        page.locator('[data-act="pilot.saveApplicability"]').click()
        expect(page.locator("#toast")).to_contain_text("路径上下文已变化")
        after = page.request.get(
            base + f"/api/v1/pilot/paths/{path['id']}", headers=headers
        ).json()["layers"][5]["applicability_revision"]
        assert after == before
        page.locator('#mFoot [data-act="ui.close"]').click()
        page.request.delete(base + f"/api/v1/pilot/paths/{path['id']}", headers=headers)
    finally:
        page.evaluate("()=>go('start',{skipOrigin:true})")
        page.wait_for_load_state("networkidle")
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
            verify_execution_readiness(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
