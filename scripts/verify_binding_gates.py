"""P2′ 真实浏览器：设计允许缺项，实际使用入口阻断并回原来源。"""

import sys
from pathlib import Path
from uuid import uuid4

from binding_gate_fixture import add_accountability, add_bindings, api_for
from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_binding_gates(page, base):
    original_viewport = page.viewport_size
    try:
        _verify_binding_gates(page, base)
    finally:
        page.set_viewport_size(original_viewport)
        page.evaluate("()=>go('start',{skipOrigin:true})")


def _verify_binding_gates(page, base):
    api, headers = api_for(page, base)
    suffix = uuid4().hex[:8]
    pos = api("POST", "/positions", {"code": "Z-GUP-" + suffix, "name": "门禁验收岗位"})
    process = api(
        "POST",
        "/process-map",
        {
            "code": "Z-GUPR-" + suffix,
            "name": "门禁验收流程",
            "level": 3,
            "publish_policy": "direct",
        },
    )
    pid = process["id"]
    activity = api(
        "POST",
        "/process-map",
        {"code": "Z-GUA-" + suffix, "name": "门禁验收活动", "level": 4, "parent_id": pid},
    )
    aid = activity["id"]
    payload = {
        "nodes": [
            {
                "node_key": "gate",
                "name": "门禁节点",
                "node_type": "TASK",
                "process_arch_id": aid,
                "owner_position_id": pos["id"],
            }
        ],
        "edges": [],
    }
    api("PUT", f"/processes/{pid}/design", payload)
    sources = add_bindings(page, base, pid, aid, pos["id"], "gate", with_a=False)
    published = api(
        "POST",
        f"/processes/{pid}/design/publish",
        {"change_note": "缺A设计仍可发布", "self_publish_reason": "仅隔离合成验证不代表业务授权"},
    )
    assert published["binding_warnings"]
    for width in [1440, 1024]:
        page.set_viewport_size({"width": width, "height": 950})
        page.evaluate("id=>go('execution',{params:{process:id,tab:'config'},skipOrigin:true})", pid)
        expect(page.locator("[data-execution-binding-gate]")).to_contain_text("执行版")
        expect(page.locator("[data-execution-binding-gate]")).to_contain_text("搭班子")
        page.locator('[data-act="ready.bindingNode"]').first.click()
        expect(page.locator("[data-node-binding]")).to_be_visible()
        page.evaluate(
            "id=>go('responsibility',{params:{position:id,tab:'description'},push:true})", pos["id"]
        )
        expect(page.locator("[data-job-binding-gate]")).to_contain_text("暂不可提交评审")
        expect(page.locator('[data-act="responsibility.compile"]')).to_be_enabled()
        page.reload(wait_until="networkidle")
        expect(page.locator("[data-job-binding-gate]")).to_contain_text("暂不可提交评审")
    reviewer = next(u for u in api("GET", "/auth/users") if u["username"] == "chen")
    data = api(
        "PUT",
        f"/execution/readiness?process_id={pid}",
        {
            "expected_revision": 0,
            "reviewer_user_id": reviewer["id"],
            "requirements": {
                k: {"mode": "NOT_APPLICABLE", "reason": "仅核对原记录载体，合成不需其他配置"}
                for k in ["forms", "assignments", "deadlines"]
            },
            "evidence": "隔离合成核对",
            "rollback_note": "停止合成新实例",
        },
    )
    login = page.request.post(
        base + "/api/v1/auth/login", data={"username": "chen", "password": "chen123"}
    ).json()
    reviewer_headers = {"Authorization": "Bearer " + login["token"]}

    def confirm(revision):
        return page.request.post(
            base + f"/api/v1/execution/readiness/confirm?process_id={pid}",
            headers=reviewer_headers,
            data={
                "expected_revision": revision,
                "decision": "ACCEPT",
                "evidence": "本人核对合成绑定",
            },
        )

    assert confirm(data["revision"]).status == 400
    preview = api("POST", f"/positions/{pos['id']}/job-description/preview", {})
    job = api(
        "POST",
        f"/positions/{pos['id']}/job-descriptions",
        {"expected_input_hash": preview["input_hash"]},
    )

    def transition(version, target):
        return page.request.post(
            base
            + f"/api/v1/process-documents/{version['document_id']}/versions/{version['version_id']}/transition",
            headers=headers,
            data={"status": target},
        )

    assert transition(job, "IN_REVIEW").status == 409
    add_accountability(api, pid, aid, pos["id"])
    api("PUT", f"/processes/{pid}/design", payload)
    api(
        "POST",
        f"/processes/{pid}/design/publish",
        {"change_note": "补齐并重新固定", "self_publish_reason": "仅隔离合成验证补齐原绑定"},
    )
    assert transition(job, "IN_REVIEW").status == 409
    current = api("GET", f"/execution/readiness?process_id={pid}")
    confirmed = confirm(current["revision"])
    assert confirmed.ok and confirmed.json()["confirmed"], confirmed.text()
    preview = api("POST", f"/positions/{pos['id']}/job-description/preview", {})
    assert preview["can_submit_review"]
    job = api(
        "POST",
        f"/positions/{pos['id']}/job-descriptions",
        {"expected_input_hash": preview["input_hash"]},
    )
    for target in ["IN_REVIEW", "APPROVED", "EFFECTIVE"]:
        response = transition(job, target)
        assert response.ok, response.text()
    api("PATCH", f"/execution/forms/{sources['form']['id']}", {"name": "合成载体修订"})
    page.evaluate("id=>go('execution',{params:{process:id,tab:'config'},skipOrigin:true})", pid)
    expect(page.locator("#executionReadiness")).to_contain_text("待复核")
    changed = api("GET", f"/execution/readiness?process_id={pid}")
    assert not changed["confirmed"] and confirm(changed["revision"]).status == 400
    viewer = page.context.browser.new_context()
    try:
        vp = viewer.new_page()
        vp.goto(base, wait_until="networkidle")
        vp.fill("#loginUser", "viewer")
        vp.fill("#loginPass", "viewer123")
        vp.click("#loginBtn")
        expect(vp.locator("#loginMask")).not_to_be_visible()
        vp.evaluate("id=>go('execution',{params:{process:id,tab:'config'},skipOrigin:true})", pid)
        expect(vp.locator("[data-execution-binding-gate]")).to_contain_text("执行版")
        assert vp.locator('[data-act="ready.edit"]').count() == 0
    finally:
        viewer.close()
    print("PASS P2′ 缺A发布、双使用入口阻断、补齐重新固定、旧草稿拒用、来源失效、1440/1024与只读")


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
        verify_binding_gates(page, base)
        assert not errors, errors
        output = Path(".superpowers/sdd/2026-11-10-binding-p2-gates")
        page.screenshot(path=str(output / "gates-execution.png"), full_page=True)
        log = (folder / "server.log").read_text(encoding="utf-8")
        (output / "gates-server.log").write_text(log, encoding="utf-8")
        assert " 500 Internal Server Error" not in log
        browser.close()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
