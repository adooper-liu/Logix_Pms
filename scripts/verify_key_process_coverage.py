"""P3b 关键过程覆盖度矩阵真实浏览器专项。"""

from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_key_process_coverage(page, base):
    token = page.evaluate("localStorage.getItem('psm_token')")
    headers = {"Authorization": "Bearer " + token}

    def api(method, path, data=None):
        response = page.request.fetch(
            base + "/api/v1" + path,
            method=method,
            headers=headers,
            data=data,
        )
        assert response.ok, f"{method} {path}: {response.status} {response.text()}"
        return response.json()

    suffix = uuid4().hex[:8]
    process = api(
        "POST",
        "/process-map",
        {
            "code": "P3BUI-P-" + suffix,
            "name": "覆盖度专项流程",
            "level": 3,
            "publish_policy": "direct",
        },
    )
    process_id = process["id"]
    activity = api(
        "POST",
        "/process-map",
        {
            "code": "P3BUI-A-" + suffix,
            "name": "覆盖度关键活动",
            "level": 4,
            "parent_id": process_id,
            "is_key_process": True,
            "key_basis": "专项验证关键订单活动",
        },
    )
    activity_id = activity["id"]
    try:
        api(
            "PUT",
            f"/processes/{process_id}/design",
            {
                "nodes": [
                    {
                        "node_key": "coverage-node",
                        "name": "覆盖度执行节点",
                        "node_type": "TASK",
                        "process_arch_id": activity_id,
                    }
                ],
                "edges": [],
            },
        )
        api(
            "POST",
            f"/processes/{process_id}/design/publish",
            {
                "change_note": "覆盖度专项发布 To-Be 模型",
                "self_publish_reason": "仅用于隔离浏览器验收，不代表生产授权",
            },
        )
        api(
            "POST",
            f"/processes/{process_id}/architecture-map/links",
            {
                "node_key": "coverage-node",
                "activity_id": activity_id,
                "relation": "REALIZES",
                "path_condition": "ALL",
                "coverage": 1,
            },
        )
        # 读取矩阵前先确认活动自身编辑路径展示并保存关键依据。
        page.evaluate(
            "code => go('map', {params: {process: code}, push: true, skipOrigin: true})",
            activity["code"],
        )
        page.wait_for_timeout(700)
        page.locator('[data-act="map.editProcess"]').click()
        expect(page.locator("#pfKeyProcess")).to_be_visible()
        expect(page.locator("#pfKeyProcess")).to_be_checked()
        expect(page.locator("#pfKeyBasis")).to_have_value("专项验证关键订单活动")
        page.locator("#mFoot [data-act='map.close']").click()

        page.locator('[data-act="map.tab"][data-tab="coverage"]').click()
        page.wait_for_selector("text=关键过程覆盖度矩阵", timeout=10000)
        expect(page.locator("#view")).to_contain_text("覆盖度关键活动")
        expect(page.locator("#view")).to_contain_text("已覆盖")
        expect(page.locator("#view")).to_contain_text("当前")
        expect(page.locator("#view")).to_contain_text("未评审")
        text = page.locator("#view").inner_text()
        assert "无重叠" not in text

        # viewer 可以读取，但没有流程编辑入口。
        context = page.context.browser.new_context(viewport={"width": 1024, "height": 950})
        viewer = context.new_page()
        try:
            viewer.goto(base, wait_until="networkidle")
            viewer.fill("#loginUser", "viewer")
            viewer.fill("#loginPass", "viewer123")
            viewer.click("#loginBtn")
            viewer.wait_for_selector("#loginMask", state="hidden")
            viewer.evaluate(
                "() => go('map', {params: {process: ''}, push: true, skipOrigin: true})"
            )
            viewer.locator('[data-act="map.tab"][data-tab="coverage"]').click()
            viewer.wait_for_selector("text=关键过程覆盖度矩阵", timeout=10000)
            expect(viewer.locator("#view")).to_contain_text("覆盖度关键活动")
            assert viewer.locator('[data-act="map.editProcess"]').count() == 0
            assert viewer.locator('[data-act="map.newChild"]').count() == 0
        finally:
            context.close()
    finally:
        page.request.delete(base + f"/api/v1/process-map/{process_id}", headers=headers)

    print("PASS P3b 关键过程编辑、覆盖度矩阵、未评审边界与 viewer 只读")


def main():
    with isolated_app() as (base, _folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle")
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        page.wait_for_selector("#loginMask", state="hidden")
        verify_key_process_coverage(page, base)
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    main()
