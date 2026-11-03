"""三类型分类：真实地图维护、继承与筛选刷新。"""

from pathlib import Path
from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_process_classification(page, base):
    source = page.request.get(base + "/static/js/views/map.js")
    assert (
        source.ok
        and source.body()
        == (Path(__file__).resolve().parents[1] / "web/js/views/map.js").read_bytes()
    ), "地图服务不是当前代码"
    token = page.evaluate("localStorage.getItem('psm_token')")
    headers = {"Authorization": "Bearer " + token}

    def api(method, path, data=None):
        response = page.request.fetch(
            base + "/api/v1" + path, method=method, headers=headers, data=data
        )
        assert response.ok, f"{method} {path}: {response.status}"
        return response.json()

    root = None
    try:
        code = "M1-" + uuid4().hex[:8]
        root = api("POST", "/process-map", {"code": code, "name": "分类专项根", "level": 1})
        child = api(
            "POST",
            "/process-map",
            {"code": code + "-C", "name": "分类专项子流程", "level": 3, "parent_id": root["id"]},
        )
        page.evaluate("() => { state.map.tree = null; }")
        # map详情沿现有编码参数打开，不改变原路由。
        page.evaluate("code => go('map', {params:{process:code}, skipOrigin:true})", root["code"])
        expect(page.locator('#mFoot [data-act="map.classify"]')).to_be_visible()

        def maintain(ident, mode, basis):
            row = api("GET", f"/process-map/{ident}")
            page.evaluate("() => { closeModal(); state.map.tree = null; }")
            page.evaluate(
                "code => go('map', {params:{process:code}, skipOrigin:true})", row["code"]
            )
            page.wait_for_load_state("networkidle")
            expect(page.locator("#mTitle")).to_contain_text(row["code"])
            expect(page.locator('#mFoot [data-act="map.classify"]')).to_be_visible()
            page.locator('#mFoot [data-act="map.classify"]').click()
            page.select_option("#classificationType", mode)
            page.fill("#classificationBasis", basis)
            with page.expect_response(
                lambda r: (
                    r.request.method == "PUT"
                    and r.url.endswith(f"/process-map/{ident}/classification")
                )
            ) as response:
                page.locator('[data-act="map.saveClassification"]').click()
            assert response.value.status == 200, response.value.text()
            page.wait_for_load_state("networkidle")
            return api("GET", f"/process-map/{ident}")

        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] is None
        maintain(root["id"], "CORE", "直接交付客户结果")
        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] == "CORE"
        maintain(child["id"], "SUPPORT", "本流程为价值链提供保障")
        assert api("GET", f"/process-map/{child['id']}")["classification_is_override"]
        page.evaluate("() => { closeModal(); state.map.tree = null; }")
        page.evaluate("() => go('map', {params:{process_type:'SUPPORT'}, skipOrigin:true})")
        expect(page.locator('#view select[data-act="map.typeFilter"]')).to_have_value("SUPPORT")
        expect(page.locator("#view")).to_contain_text("路径上下文")
        page.reload(wait_until="networkidle")
        expect(page.locator('#view select[data-act="map.typeFilter"]')).to_have_value("SUPPORT")
        maintain(child["id"], "UNCLASSIFIED", "范围尚待业务确认")
        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] is None
        maintain(child["id"], "INHERIT", "")
        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] == "CORE"
        maintain(root["id"], "MANAGEMENT", "本支路经营治理")
        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] == "MANAGEMENT"
        # 旧分类弹窗不得覆盖其他会话已保存的修订，输入必须保留。
        page.evaluate("code => go('map', {params:{process:code}, skipOrigin:true})", child["code"])
        expect(page.locator('#mFoot [data-act="map.classify"]')).to_be_visible()
        page.locator('#mFoot [data-act="map.classify"]').click()
        stale = api("GET", f"/process-map/{child['id']}")
        api(
            "PUT",
            f"/process-map/{child['id']}/classification",
            {
                "process_type": "CORE",
                "classification_basis": "其他会话确认",
                "classification_inherit": True,
                "expected_revision": stale["classification_revision"],
            },
        )
        page.select_option("#classificationType", "SUPPORT")
        page.fill("#classificationBasis", "保留本次输入")
        page.locator('[data-act="map.saveClassification"]').click()
        expect(page.locator("#classificationError")).to_contain_text("分类已被更新")
        expect(page.locator("#classificationBasis")).to_have_value("保留本次输入")
        assert api("GET", f"/process-map/{child['id']}")["effective_process_type"] == "CORE"
        page.evaluate("() => closeModal()")
        maintain(child["id"], "INHERIT", "")
        maintain(root["id"], "CORE", "客户价值恢复确认")
        page.evaluate(
            "id => go('process_card', {params:{process:String(id)}, skipOrigin:true})", child["id"]
        )
        expect(page.locator("#view .pc-head")).to_contain_text("核心流程")
        expect(page.locator("#view .pc-head")).to_contain_text(root["code"])
        print("OK   M1a：分类维护、继承/例外/阻断、筛选刷新与流程卡")
    finally:
        page.evaluate("() => closeModal()")
        if root:
            api("DELETE", f"/process-map/{root['id']}")
        page.evaluate(
            "() => { state.map.tree = null; state.map.typeFilter = ''; go('start', {skipOrigin:true}); }"
        )


def main():
    with isolated_app() as (base, _folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(base, wait_until="networkidle")
            page.fill("#loginUser", "admin")
            page.fill("#loginPass", "admin123")
            page.click("#loginBtn")
            expect(page.locator("#loginMask")).not_to_be_visible()
            verify_process_classification(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
