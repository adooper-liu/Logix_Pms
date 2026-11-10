"""P2真实页面：岗位职责、责任书生成与原评审链。"""

from uuid import uuid4

from binding_gate_fixture import add_bindings
from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_binding_p2(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}

    def api(method, path, data=None):
        response = page.request.fetch(
            base + "/api/v1" + path, method=method, headers=headers, data=data
        )
        assert response.ok, response.text()
        return response.json()

    suffix = uuid4().hex[:7]
    for index in range(3):
        pos = api(
            "POST", "/positions", {"code": f"P2POS-{suffix}-{index}", "name": f"P2职责岗位{index}"}
        )
        process = api(
            "POST",
            "/process-map",
            {
                "code": f"P2P-{suffix}-{index}",
                "name": "P2合成职责流程",
                "level": 3,
                "publish_policy": "direct",
            },
        )
        activity = api(
            "POST",
            "/process-map",
            {
                "code": f"P2A-{suffix}-{index}",
                "name": "岗位负责活动",
                "level": 4,
                "parent_id": process["id"],
            },
        )
        model = api(
            "PUT",
            f"/processes/{process['id']}/design",
            {
                "nodes": [
                    {
                        "node_key": "job",
                        "name": "责任节点",
                        "node_type": "TASK",
                        "process_arch_id": activity["id"],
                        "owner_position_id": pos["id"],
                    }
                ],
                "edges": [],
            },
        )
        add_bindings(page, base, process["id"], activity["id"], pos["id"], "job")
        api(
            "POST",
            f"/processes/{process['id']}/design/publish",
            {
                "expected_version": model["version"],
                "change_note": "P2合成职责发布",
                "self_publish_reason": "仅本地合成验收由同一账号发布",
            },
        )
        page.evaluate(
            "id=>go('responsibility',{params:{position:id,period:'2026-10-01'},push:true})",
            pos["id"],
        )
        expect(page.locator("[data-responsibility-overview]")).to_contain_text(pos["name"])
        page.locator('[data-act="responsibility.tab"][data-tab="activities"]').click()
        expect(page.locator("[data-responsibility-activities]")).to_contain_text("岗位负责活动")
        page.locator('[data-act="responsibility.node"]').first.click()
        expect(page.locator("[data-node-binding]")).to_be_visible()
        expect(page.locator("[data-node-binding]")).to_contain_text("当前已保存模型")
        page.evaluate(
            "id=>go('responsibility',{params:{position:id,period:'2026-10-01',tab:'description'},push:true})",
            pos["id"],
        )
        expect(page.locator('[data-act="responsibility.compile"]')).to_be_enabled()
        page.locator("details").filter(has=page.locator('a[href*="#designer?"]')).first.locator(
            "summary"
        ).click()
        source_link = page.locator('a[href*="#designer?"]').first
        assert source_link.get_attribute("href").startswith(base + "/#designer?")
        assert "basis=" in source_link.get_attribute("href")
        source_link.click()
        expect(page.locator("[data-node-binding]")).to_be_visible()
        page.evaluate(
            "id=>go('responsibility',{params:{position:id,period:'2026-10-01',tab:'description'},push:true})",
            pos["id"],
        )
        expect(page.locator('[data-act="responsibility.compile"]')).to_be_enabled()
        page.locator('[data-act="responsibility.compile"]').click()
        expect(page.locator("[data-responsibility-versions]")).to_contain_text("草稿")
        for target in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
            page.locator(
                f'[data-act="responsibility.transition"][data-status="{target}"]'
            ).first.click()
            expect(page.locator("[data-responsibility-versions]")).to_contain_text(
                {"IN_REVIEW": "评审", "APPROVED": "批准", "EFFECTIVE": "生效"}[target]
            )
        page.reload(wait_until="networkidle")
        expect(page.locator("[data-responsibility-versions]")).to_contain_text("job-description/v1")
    page.evaluate("()=>go('responsibility',{params:{},push:true})")
    expect(page.locator("[data-responsibility-select]")).to_be_visible()


def main():
    with isolated_app() as (base, folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base, wait_until="networkidle")
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        expect(page.locator("#loginMask")).not_to_be_visible()
        verify_binding_p2(page, base)
        assert not errors, errors
        print("PASS P2 三岗位职责、责任书生成、原评审生效与刷新")
        browser.close()


if __name__ == "__main__":
    main()
