"""M5原流程卡创建/固定薄轮次及冻结值刷新验证。"""

from uuid import uuid4

from frontend_test_app import isolated_app
from playwright.sync_api import expect, sync_playwright


def verify_improvement_round(page, base):
    headers = {"Authorization": "Bearer " + page.evaluate("localStorage.getItem('psm_token')")}
    me = page.request.get(base + "/api/v1/auth/me", headers=headers).json()
    pid = page.request.post(
        base + "/api/v1/process-map",
        headers=headers,
        data={
            "code": "RNDUI-" + uuid4().hex[:8],
            "name": "M5轮次自检",
            "level": 3,
            "owner_user_id": me["id"],
        },
    ).json()["id"]
    model = page.request.put(
        base + f"/api/v1/processes/{pid}/design",
        headers=headers,
        data={"nodes": [{"node_key": "a", "name": "活动", "node_type": "TASK"}], "edges": []},
    ).json()
    page.request.post(
        base + f"/api/v1/processes/{pid}/design/freeze",
        headers=headers,
        data={"expected_version": model["version"], "note": "M5前侧"},
    )
    kpi = page.request.post(
        base + "/api/v1/monitor/kpis",
        headers=headers,
        data={
            "code": "RNDUIK-" + uuid4().hex[:8],
            "name": "M5原指标",
            "dimension": "EFFICIENCY",
            "process_id": pid,
            "unit": "小时",
            "formula": "合格样本均值",
        },
    ).json()
    sample = page.request.post(
        base + f"/api/v1/monitor/kpis/{kpi['id']}/records",
        headers=headers,
        data={"period": "2026-10-01", "value": 14, "note": "前侧原样本"},
    ).json()
    page.evaluate(
        "pid=>go('process_card',{params:{process:String(pid),module:'rounds'},skipOrigin:true})",
        pid,
    )
    expect(page.locator("#roundComparison")).to_contain_text("轮次对照")
    page.locator('[data-act="round.new"]').click()
    expect(page.locator("#rdName")).to_be_visible()
    page.fill("#rdName", "M5本轮")
    page.fill("#rdScope", "同一客户群组")
    page.select_option("#rdModel", str(model["version_id"]))
    page.select_option("#rdMetric", str(kpi["id"]))
    page.fill("#rdStart", "2026-10-01")
    page.fill("#rdEnd", "2026-10-31")
    for field in ["Semantics", "Source", "Calendar", "Quality"]:
        page.fill("#rd" + field, "M5-" + field)
    page.select_option("#rdSamples", [str(sample["id"])])
    with page.expect_response(
        lambda r: r.request.method == "POST" and r.url.endswith("/improvement-rounds")
    ) as created:
        page.locator('[data-act="round.save"]').click()
    assert created.value.status == 201, created.value.text()
    rid = created.value.json()["id"]
    expect(page.locator("#roundComparison")).to_contain_text("前侧草稿")
    page.locator('[data-act="round.action"][data-action="lock-baseline"]').click()
    expect(page.locator("#roundComparison")).to_contain_text("前侧已固定")
    assert page.locator('[data-act="round.edit"]').count() == 0
    page.request.post(
        base + f"/api/v1/monitor/kpis/{kpi['id']}/records",
        headers=headers,
        data={"period": "2026-10-01", "value": 999, "note": "后续修正"},
    )
    page.reload(wait_until="networkidle")
    expect(page.locator("#roundComparison")).to_contain_text("14")
    assert "999" not in page.inner_text("#roundComparison")
    assert "round=" + str(rid) in page.url
    expect(page.locator("#roundComparison")).to_contain_text("待原业务核验")
    second_payload = {
        "name": "第二轮草稿",
        "scope_note": "同流程另一轮",
        "asis_model_version_id": model["version_id"],
        "baseline_window": {"start": "2026-10-01", "end": "2026-10-31"},
        "metrics": [
            {
                "kpi_id": kpi["id"],
                "source_semantics": "原语义",
                "source_evidence": "原依据",
                "calendar": "自然日",
            }
        ],
        "baseline_samples": [
            {"record_id": sample["id"], "source_evidence": "原样本", "quality_note": "已核"}
        ],
    }
    other = page.request.post(
        base + f"/api/v1/processes/{pid}/improvement-rounds", headers=headers, data=second_payload
    ).json()
    page.locator('[data-act="round.after"]').click() if page.locator(
        '[data-act="round.after"]'
    ).count() else None
    # 同流程换轮次也必须拒绝旧表单，不能只比较process。
    page.locator('[data-act="round.acceptance"]').click()
    expect(page.locator("#raTarget")).to_be_visible()
    page.fill("#raTarget", "旧轮次约定")
    page.fill("#raRed", "红线")
    page.fill("#raObservation", "原观察")
    requests = []

    def observe(request):
        if request.method == "POST" and "/lock-acceptance" in request.url:
            requests.append(request.url)

    page.on("request", observe)
    page.evaluate(
        "args=>go('process_card',{params:{process:String(args[0]),module:'rounds',round:String(args[1])},skipOrigin:true})",
        [pid, other["id"]],
    )
    page.wait_for_timeout(700)
    page.wait_for_load_state("networkidle")
    page.locator('[data-act="round.append"]').click()
    page.wait_for_timeout(400)
    assert not requests, "同流程换轮次后仍提交旧表单"
    page.remove_listener("request", observe)
    page.evaluate("()=>closeModal()")
    # 有轮次保留保护的临时业务不得在真实服务强删；专项用独立浏览器/临时服务。
    # 在同一全站服务中保留原记录，覆盖率测试应以当前原API为依据而非硬编码28。
    page.evaluate("()=>go('start',{skipOrigin:true})")
    page.wait_for_load_state("networkidle")
    print("OK   M5：原流程卡无项目建轮、前侧固定、原值改后快照不变、刷新选轮次与待业务核验")


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
            verify_improvement_round(page, base)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
