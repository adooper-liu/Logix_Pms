"""经营绑定 P0：驱动真实设计器、节点角标与只读访问。"""

import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def verify_binding_readiness(page, base):
    page.evaluate("window.go('designer', {params: {process: null}, push: true})")
    page.wait_for_selector('[data-act="designer.process"]')
    pid = int(page.locator('[data-act="designer.process"]').input_value())
    page.locator('[data-act="designer.tab"][data-tab="binding"]').click()
    expect(page.locator("[data-binding-summary]")).to_be_visible()
    expect(page.locator("[data-binding-summary]")).to_contain_text("只读")
    page.locator(".fold-card > summary").filter(has_text="L4-").first.click()
    expect(page.locator('[data-binding-facet="GOAL"]').first).to_be_visible()
    expect(page.locator('[data-binding-facet="TEAM"]').first).to_contain_text("RACI")
    page.reload(wait_until="networkidle")
    expect(page.locator("[data-binding-summary]")).to_be_visible()
    assert "tab=binding" in page.url
    page.locator('[data-act="designer.tab"][data-tab="model"]').click()
    page.wait_for_selector(".djs-element.pms-bind-yellow, .djs-element.pms-bind-red")
    markers = page.locator(".djs-element.pms-bind-yellow, .djs-element.pms-bind-red")
    key = markers.first.get_attribute("data-element-id")
    # marker覆盖层是用户可点击入口，不修改BPMN命令栈。
    page.locator(f'[data-binding-marker="{key}"]').click()
    expect(page.locator("[data-node-binding]")).to_be_visible()
    expect(
        page.locator('[data-act="designer.propSection"][data-section="binding"]')
    ).to_have_attribute("aria-selected", "true")
    assert (
        page.locator(
            "[data-node-binding] input, [data-node-binding] textarea, [data-node-binding] select"
        ).count()
        == 0
    )
    assert page.evaluate("window.__bpmnSpike.modeler.get('commandStack').canUndo()") is False
    # 原属性保存后绑定必须按新版本刷新，不保留旧估计。
    page.locator('[data-act="designer.propSection"][data-section="metrics"]').click()
    original_duration = page.locator("#bpDur").input_value()
    page.locator("#bpDur").fill(str(float(original_duration) + 1))
    page.locator('[data-act="designer.saveMetrics"]').click()
    try:
        page.wait_for_function(
            "() => window.state.designer.binding?.model_version === window.state.designer.model.draft_version && window.state.designer.model.status === 'DRAFT'",
            timeout=10000,
        )
    finally:
        page.locator("#bpDur").fill(original_duration)
        page.locator('[data-act="designer.saveMetrics"]').click()
        page.wait_for_timeout(400)
    # 切换流程后旧结果不可残留。
    options = page.locator('[data-act="designer.process"] option').evaluate_all(
        "els => els.map(e => e.value)"
    )
    other = next((value for value in options if int(value) != pid), None)
    if other:
        page.locator('[data-act="designer.process"]').select_option(other)
        page.wait_for_function(
            "id => window.state.designer.binding?.process_id === Number(id)", arg=other
        )
        assert page.evaluate("window.state.designer.binding.process_id") == int(other)
    page.evaluate(
        "id => window.go('designer', {params: {process: id, tab: 'binding'}, push: true})", pid
    )
    expect(page.locator("[data-binding-summary]")).to_contain_text("6 个活动")
    # 先构造上一画布实例，再切绑定列表；定位不能落到已离屏的实例。
    page.locator('[data-act="designer.tab"][data-tab="model"]').click()
    page.wait_for_selector("[data-binding-marker]")
    page.locator('[data-act="designer.tab"][data-tab="binding"]').click()
    expect(page.locator("[data-binding-summary]")).to_be_visible()
    # 绑定列表的定位必须切回画布，不向离屏旧modeler选择。
    page.locator(".fold-card > summary").filter(has_text="L4-").first.click()
    page.locator('[data-act="designer.bindingLocate"]').first.click()
    expect(page.locator("[data-node-binding]")).to_be_visible()
    expect(page.locator("#bpmnCanvas")).to_be_visible()
    page.locator('[data-act="designer.tab"][data-tab="binding"]').click()
    pending = []
    pattern = "**/api/v1/processes/*/binding-readiness"
    page.route(pattern, lambda route: pending.append(route))
    page.locator('[data-act="designer.tab"][data-tab="model"]').click()
    page.wait_for_function("true")
    for _ in range(50):
        if pending:
            break
        page.wait_for_timeout(50)
    assert pending
    page.evaluate("window.go('workbench', {push: true})")
    pending.pop().continue_()
    page.unroute(pattern)
    page.wait_for_timeout(300)
    assert page.evaluate("window.state.view") == "workbench"
    # 独立只读会话不继承管理员localStorage。
    context = page.context.browser.new_context(viewport={"width": 1366, "height": 1000})
    viewer = context.new_page()
    writes = []
    try:
        viewer.on(
            "console",
            lambda message: (
                print("VIEWER_CONSOLE", message.text) if message.type == "error" else None
            ),
        )
        viewer.on("pageerror", lambda error: print("VIEWER_ERROR", error))
        viewer.on(
            "response",
            lambda response: (
                print("VIEWER_HTTP", response.status, response.url)
                if response.status >= 400
                else None
            ),
        )
        viewer.goto(base, wait_until="networkidle")
        viewer.fill("#loginUser", "viewer")
        viewer.fill("#loginPass", "viewer123")
        viewer.click("#loginBtn")
        viewer.wait_for_selector("#loginMask", state="hidden")
        viewer.evaluate(
            "id => window.go('designer', {params: {process: id, tab: 'binding'}, push: true})", pid
        )
        expect(viewer.locator("[data-binding-summary]")).to_be_visible()
        assert viewer.locator('[data-act="designer.publish"]').count() == 0
        viewer.on(
            "request",
            lambda req: (
                writes.append(req.url) if req.method in {"PUT", "PATCH", "DELETE"} else None
            ),
        )
        viewer.locator('[data-act="designer.tab"][data-tab="model"]').click()
        try:
            viewer.wait_for_selector("[data-binding-marker]", timeout=10000)
        except Exception:
            print("VIEWER_STATE", viewer.locator("body").inner_text()[-7000:])
            raise
        viewer.locator("[data-binding-marker]").first.click()
        expect(viewer.locator("[data-node-binding]")).to_be_visible()
        assert not writes, writes
        assert viewer.locator("[data-node-binding] input, [data-node-binding] select").count() == 0
    finally:
        context.close()
    page.evaluate("window.go('workbench', {push: true})")


def main():
    base = sys.argv[1]
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        errors = []
        page.on("pageerror", lambda err: errors.append(str(err)))
        page.goto(base, wait_until="networkidle")
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        page.wait_for_selector("#loginMask", state="hidden")
        verify_binding_readiness(page, base)
        assert not errors, errors
        page.evaluate("window.go('designer', {params: {tab: 'binding'}, push: true})")
        expect(page.locator("[data-binding-summary]")).to_be_visible()
        target = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("var/binding-p0.png")
        target.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(target), full_page=True)
        browser.close()
    print("PASS P0: binding sources, markers, node panel, refresh, process switch and viewer")


if __name__ == "__main__":
    main()
