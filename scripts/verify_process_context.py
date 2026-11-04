"""M3实际界面：原章程、SIPOC交接与本人确认。"""

from pathlib import Path
from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_process_context(page, base):
    for module in ["views/process_card.js", "views/shared/tool_sheet.js"]:
        response = page.request.get(base + "/static/js/" + module)
        assert (
            response.body()
            == (Path(__file__).resolve().parents[1] / "web/js" / module).read_bytes()
        )
    token = page.evaluate("localStorage.getItem('psm_token')")
    headers = {"Authorization": "Bearer " + token}
    rows = page.request.get(base + "/api/v1/process-map/flat?level=3", headers=headers).json()
    proc = next(row for row in rows if row["code"] == "L3-032")
    receiver = next(row for row in rows if row["code"] == "L3-033")
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    if not proc["owner_user_id"]:
        assert page.request.patch(
            base + f"/api/v1/process-map/{proc['id']}",
            headers=headers,
            data={"owner_user_id": me["id"]},
        ).ok
    page.evaluate(
        "pid=>go('process_card',{params:{process:String(pid),module:'context'},skipOrigin:true})",
        proc["id"],
    )
    page.locator('[data-act="process_card.selectModule"][data-module="context"]').click()
    expect(page.locator("#processContext")).to_contain_text("边界与交接")
    page.locator('[data-act="context.editCharter"]').click()
    expect(page.locator("#ccPurpose")).to_be_visible()
    for field in [
        "Purpose",
        "Starts",
        "Ends",
        "In",
        "Out",
        "Stop",
        "Customer",
        "Result",
        "Resources",
    ]:
        page.locator("#cc" + field).fill("M3自检-" + field)
    page.select_option("#ccSponsor", str(me["id"]))
    page.locator('[data-act="context.saveCharter"]').click()
    expect(page.locator("#processContext")).to_contain_text("M3自检-Customer")
    page.reload(wait_until="networkidle")
    expect(page.locator("#processContext")).to_contain_text("M3自检-Result")
    page.locator('[data-act="context.editCharter"]').click()
    expect(page.locator("#ccPurpose")).to_be_visible()
    page.fill("#ccPurpose", "不得写入接收流程的旧弹窗内容")
    requests = []

    def record(request):
        if request.method == "PUT" and "/start/charters/" in request.url:
            requests.append(request.url)

    page.on("request", record)
    page.evaluate(
        "pid=>go('process_card',{params:{process:String(pid),module:'context'},skipOrigin:true})",
        receiver["id"],
    )
    page.wait_for_timeout(700)
    page.wait_for_load_state("networkidle")
    page.locator('[data-act="context.saveCharter"]').click()
    page.wait_for_timeout(500)
    assert not requests, "旧章程弹窗向新流程发起写入"
    page.remove_listener("request", record)
    page.evaluate("()=>closeModal()")
    page.evaluate(
        "pid=>go('process_card',{params:{process:String(pid),module:'context'},skipOrigin:true})",
        proc["id"],
    )
    expect(page.locator("#processContext")).to_contain_text("M3自检-Customer")
    page.locator('[data-act="context.newHandoff"]').click()
    expect(page.locator("#tsHandoff")).to_be_visible()
    page.locator("#tsHandoff").check()
    expect(page.locator("#tsReceiverProcess")).to_be_visible()
    page.select_option("#tsReceiverProcess", str(receiver["id"]))
    page.select_option("#tsProvider", str(me["id"]))
    page.select_option("#tsReceiver", str(me["id"]))
    for field in ["Quality", "Timing", "Exception"]:
        page.fill("#ts" + field, "M3自检-" + field)
    form = page.request.get(base + "/api/v1/tools/SIPOC/sheet-form", headers=headers).json()
    for field in form["fields"]:
        page.fill("#ts-" + field["key"], "M3交接-" + uuid4().hex[:8])
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/tools/SIPOC/sheets")
    ) as saved:
        page.locator('#mFoot [data-act="toolbox.submitSheet"]').click()
    assert saved.value.status == 201, saved.value.text()
    sheet = saved.value.json()
    expect(page.locator("#processContext")).to_contain_text("待双方确认")
    for side in ["provider", "receiver"]:
        page.locator(
            f'[data-act="context.confirm"][data-id="{sheet["id"]}"][data-side="{side}"]'
        ).click()
        page.fill("#hcEvidence", "核对真实原记录-" + side)
        with page.expect_response(
            lambda r: r.request.method == "POST" and r.url.endswith("/confirm")
        ) as confirmed:
            page.locator('[data-act="context.submitConfirm"]').click()
        assert confirmed.value.status == 200, confirmed.value.text()
        expect(page.locator("#processContext")).to_contain_text(
            "待接收方确认" if side == "provider" else "双方已确认"
        )
        page.wait_for_load_state("networkidle")
        expect(page.locator("#mask")).not_to_have_class("mask show")
    expect(page.locator("#processContext")).to_contain_text("双方已确认")
    page.evaluate(
        "pid=>go('process_card',{params:{process:String(pid),module:'context'},skipOrigin:true})",
        receiver["id"],
    )
    expect(page.locator("#processContext")).to_contain_text("双方已确认")
    page.evaluate("()=>go('start',{skipOrigin:true})")
    page.wait_for_load_state("networkidle")
    print("OK   M3：原章程客户结果/刷新、无项目SIPOC交接、本人双方确认与接收流程反查")


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
            verify_process_context(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
