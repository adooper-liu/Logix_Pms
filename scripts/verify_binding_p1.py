"""P1 真实设计器活动责任、原资源维护与冻结提示。"""

from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_binding_p1(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    suffix = uuid4().hex[:8]

    def api(method, path, data=None):
        response = page.request.fetch(
            base + "/api/v1" + path, method=method, headers=headers, data=data
        )
        assert response.ok, response.text()
        return response.json()

    process = api(
        "POST", "/process-map", {"code": "P1UI-" + suffix, "name": "P1绑定自检", "level": 3}
    )
    pid = process["id"]
    activity = api(
        "POST",
        "/process-map",
        {"code": "P1A-" + suffix, "name": "自检活动", "level": 4, "parent_id": pid},
    )
    position = api("POST", "/positions", {"code": "P1POS-" + suffix, "name": "P1合成负责岗位"})
    role = api("POST", "/governance/roles", {"code": "P1ROLE-" + suffix, "name": "P1合成负责角色"})
    member = api(
        "POST",
        "/auth/users",
        {
            "username": "p1-member-" + suffix,
            "display_name": "P1合成成员",
            "password": "Synthetic-Only-48!",
            "role": "OWNER",
            "position_id": position["id"],
        },
    )
    api("POST", f"/governance/roles/{role['id']}/members", {"user_id": member["id"]})
    form = None
    try:
        api(
            "PUT",
            f"/processes/{pid}/design",
            {
                "nodes": [
                    {
                        "node_key": "a",
                        "name": "活动节点",
                        "node_type": "TASK",
                        "process_arch_id": activity["id"],
                    }
                ],
                "edges": [],
            },
        )
        form = api(
            "POST",
            "/execution/forms",
            {"process_id": pid, "node_key": "a", "name": "P1原记录", "fields": []},
        )
        page.evaluate("id=>go('designer',{params:{process:id,tab:'binding'},push:true})", pid)
        expect(page.locator("[data-binding-summary]")).to_be_visible()
        page.locator('[data-act="designer.bindingEdit"]').first.click()
        expect(page.locator("#bindingActivity")).to_have_value(str(activity["id"]))
        page.select_option("#bindingRole", str(role["id"]))
        page.select_option("#bindingRaci", "A")
        page.locator('[data-act="designer.bindingSaveRaci"]').click()
        expect(page.locator("#bindingEditRecords")).to_contain_text(role["name"])
        second = api("GET", "/governance/roles?active_only=true")[1]
        page.select_option("#bindingRole", str(second["id"]))
        page.locator('[data-act="designer.bindingSaveRaci"]').click()
        expect(page.locator("#bindingEditError")).to_contain_text("已有 A")
        page.select_option("#bindingResource", f"FORM:{form['id']}")
        page.locator('[data-act="designer.bindingSaveResource"]').click()
        expect(page.locator("#bindingEditRecords")).to_contain_text("P1原记录")
        page.locator('#mFoot [data-act="ui.close"]').click()
        page.locator('[data-act="designer.tab"][data-tab="raci"]').click()
        expect(page.locator("#view")).to_contain_text(f"ACTIVITY:{activity['id']}")
        page.locator('[data-act="designer.tab"][data-tab="binding"]').click()
        expect(page.locator("[data-binding-consistency]")).to_contain_text("待确认")
        model = api("GET", f"/processes/{pid}/design")
        api(
            "POST",
            f"/processes/{pid}/design/freeze",
            {"expected_version": model["version"], "note": "合成UI固定"},
        )
        page.reload(wait_until="networkidle")
        expect(page.locator("[data-binding-consistency]")).to_contain_text("一致")
        api("PATCH", f"/execution/forms/{form['id']}", {"name": "P1原记录修订"})
        page.reload(wait_until="networkidle")
        expect(page.locator("[data-binding-consistency]")).to_contain_text("待确认")
        # 关闭维护后首屏立即展示最新一致性，不靠切页签刷新。
        page.locator('[data-act="designer.bindingEdit"]').first.click()
        page.locator('[data-act="designer.bindingRemoveResource"]').click()
        expect(page.locator("#bindingEditRecords")).not_to_contain_text("P1原记录")
        page.locator('#mFoot [data-act="ui.close"]').click()
        expect(page.locator("[data-binding-consistency]")).to_contain_text("失效")
        # 旧弹窗切流程后不提交。
        page.locator('[data-act="designer.bindingEdit"]').first.click()
        writes = []
        page.on(
            "request",
            lambda req: (
                writes.append(req.url)
                if req.method == "POST"
                and ("resource-links" in req.url or "/governance/raci" in req.url)
                else None
            ),
        )
        page.evaluate("go('start',{skipOrigin:true})")
        page.wait_for_load_state("networkidle")
        if page.locator('[data-act="designer.bindingSaveRaci"]').is_visible():
            page.locator('[data-act="designer.bindingSaveRaci"]').click()
            expect(page.locator("#bindingEditError")).to_contain_text("已变化")
        else:
            assert page.locator("#mask.show").count() == 0
        assert not writes, writes
        page.evaluate("closeModal()")
        context = page.context.browser.new_context()
        try:
            viewer = context.new_page()
            viewer.goto(base, wait_until="networkidle")
            viewer.fill("#loginUser", "viewer")
            viewer.fill("#loginPass", "viewer123")
            viewer.click("#loginBtn")
            viewer.wait_for_selector("#loginMask", state="hidden")
            viewer.evaluate("id=>go('designer',{params:{process:id,tab:'binding'},push:true})", pid)
            expect(viewer.locator("[data-binding-summary]")).to_be_visible()
            assert viewer.locator('[data-act="designer.bindingEdit"]').count() == 0
        finally:
            context.close()
        print("OK P1: 活动唯一A/重复拒绝、原表单引用、权责同步、冻结变化、旧弹窗与只读")
    finally:
        page.evaluate("closeModal()")
        links = api("GET", f"/processes/{pid}/resource-links")
        for link in links:
            api("DELETE", f"/processes/{pid}/resource-links/{link['id']}")
        matrix = api("GET", f"/governance/raci?process_id={pid}")
        for group in matrix["matters"]:
            for row in group["entries"]:
                api("DELETE", f"/governance/raci/{row['id']}")
        if form:
            api("DELETE", f"/execution/forms/{form['id']}")
        api("DELETE", f"/process-map/{pid}")
        page.evaluate("go('workbench',{skipOrigin:true})")


def main():
    with isolated_app() as (base, _folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base, wait_until="networkidle")
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        page.wait_for_selector("#loginMask", state="hidden")
        try:
            verify_binding_p1(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
