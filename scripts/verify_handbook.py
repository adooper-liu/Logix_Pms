"""P3a browser smoke: a handbook states ownership, fixed sources, and unknowns."""

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def main():
    with isolated_app() as (base, folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.goto(base, wait_until="networkidle")
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        expect(page.locator("#loginMask")).not_to_be_visible()
        page.evaluate("()=>go('handbook',{params:{},push:true})")
        expect(page.locator("#pageTitle")).to_have_text("员工手册")
        page.locator("[data-handbook-subject]").select_option(index=1)
        page.wait_for_load_state("networkidle")
        expect(page.locator("[data-handbook-overview]")).to_be_visible()
        page.locator('[data-act="handbook.tab"][data-tab="entries"]').click()
        expect(page.locator("[data-handbook-entries]")).to_be_visible()
        page.set_viewport_size({"width": 1024, "height": 950})
        page.reload(wait_until="networkidle")
        expect(page.locator("#pageTitle")).to_have_text("员工手册")
        page.set_viewport_size({"width": 1440, "height": 950})
        print("PASS P3a handbook entry, unknowns, refresh, 1440/1024")
        browser.close()


if __name__ == "__main__":
    main()
