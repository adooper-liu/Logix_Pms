"""前端联调自检。

两段：
  1. 视图渲染 —— 八个视图各点一遍，收集 JS 报错与失败请求，并截图
  2. 交互路径 —— 驱动关键交互（模态框、页签、表单提交、下钻），断言真实渲染结果

用法：
    python scripts/verify_frontend.py [http://127.0.0.1:8123] [截图输出目录]
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

# Windows 控制台默认是 GBK，中文输出会变乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VIEWS = [
    ("dashboard", "管理驾驶舱"),
    ("map", "企业流程地图"),
    ("workflow", "五阶段标准工作流"),
    ("projects", "流程项目组合"),
    ("toolbox", "方法论工具箱"),
    ("designer", "流程设计器"),
    ("monitor", "运营监控与KPI"),
    ("knowledge", "流程知识库"),
    ("execution", "流程执行"),
]

failures: list[str] = []


def check(name: str, fn) -> None:
    try:
        fn()
        print(f"OK   {name}")
    except Exception as exc:  # noqa: BLE001 —— 自检脚本，任何异常都算失败
        failures.append(name)
        print(f"FAIL {name}: {type(exc).__name__}: {exc}")


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8123"
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    console_errors: list[str] = []
    page_errors: list[str] = []
    failed_requests: list[str] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})

        page.on(
            "console",
            lambda m: console_errors.append(f"[{m.type}] {m.text}") if m.type == "error" else None,
        )
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        page.on(
            "response",
            lambda r: (
                failed_requests.append(f"{r.status} {r.request.method} {r.url}")
                if r.status >= 400
                else None
            ),
        )

        page.goto(base + "/", wait_until="networkidle")
        page.wait_for_timeout(400)

        # 先登录（除登录接口外全部业务接口都需要令牌）
        assert page.is_visible("#loginMask"), "未登录时应显示登录页"
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        page.wait_for_timeout(1500)
        assert not page.is_visible("#loginMask"), "登录成功后登录页应隐藏"
        assert page.inner_text("#userName").strip() != "未登录", "登录后顶栏应显示当前用户"
        assert page.inner_text("#backendState").strip() == "后端已连接"
        print(f"登录成功：{page.inner_text('#userName')}（{page.inner_text('#userRole')}）\n")

        # ---------------------------------------------------- 第一段：视图渲染
        print("── 视图渲染 ──")
        for view, _title in VIEWS:
            page.click(f'.nav a[data-view="{view}"]')
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(600)

            text = page.inner_text("#view").strip()
            nodes = page.eval_on_selector_all("#view *", "els => els.length")
            ok = len(text) > 30 and "加载失败" not in text
            if not ok:
                failures.append(f"view:{view}")
            first_line = text.splitlines()[0][:56] if text else "(空)"
            print(f"{'OK ' if ok else 'FAIL'} {view:<10} 节点 {nodes:>5}  {first_line}")
            page.screenshot(path=str(out_dir / f"{view}.png"), full_page=True)

        # ---------------------------------------------------- 第二段：交互路径
        print("\n── 交互路径 ──")

        def close_modal() -> None:
            """不同弹窗的取消按钮文案不一样（关闭 / 取消），统一处理。"""
            for label in ("关闭", "取消"):
                btn = page.locator(f'#mFoot button:has-text("{label}")')
                if btn.count() > 0:
                    btn.first.click()
                    page.wait_for_timeout(400)
                    return
            page.evaluate("() => closeModal()")
            page.wait_for_timeout(200)

        def goto(view: str) -> None:
            # 上一个检查可能留下未关的弹窗，遮罩会挡住导航点击
            page.evaluate("() => closeModal()")
            page.wait_for_timeout(150)
            page.click(f'.nav a[data-view="{view}"]')
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(600)

        # 地图下钻
        def map_drill() -> None:
            goto("map")
            before = page.inner_text(".crumb")
            page.click("#view tr.map-row >> nth=2")
            page.wait_for_timeout(700)
            after = page.inner_text(".crumb")
            assert len(after) > len(before), f"面包屑未增长：{before!r} → {after!r}"
            assert page.inner_text("#view").count("Owner:") > 0

        # 对标框架：同一层流程切换 SCOR / APQC，覆盖率应有差异
        def benchmark_switch() -> None:
            goto("map")
            page.select_option("#view select[title='切换对标框架']", "SCOR")
            page.wait_for_selector("#view :text('对标覆盖')", timeout=8000)
            text = page.inner_text("#view")
            assert "24/28" in text, f"SCOR 覆盖率渲染异常：{text[:160]!r}"
            assert "L3-010" in text, "SCOR 应显示研发类未覆盖流程"

            page.select_option("#view select[title='切换对标框架']", "APQC_PCF")
            page.wait_for_selector("#view :text('28/28')", timeout=8000)
            text = page.inner_text("#view")
            assert "所有 L3 流程" in text, f"APQC 应全量覆盖：{text[:160]!r}"

            page.click("#view .map-bench-pill >> nth=0")
            page.wait_for_selector("#mBody table")
            assert "编码" in page.inner_text("#mBody")
            close_modal()

        # 标准工作流：步骤详情
        def workflow_step_modal() -> None:
            goto("workflow")
            page.click("#view .step >> nth=0")
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "标准动作" in body and "关键要点" in body, body[:120]
            close_modal()
            page.wait_for_timeout(300)

        # 方法论匹配引擎（真实调用后端）
        def workflow_recommend() -> None:
            goto("workflow")
            page.click('#view .seg button:has-text("方法论匹配")')
            page.wait_for_timeout(500)
            page.select_option("#rcState", "SEVERE_OUTDATED")
            page.fill("#rcPct", "60")
            page.select_option("#rcScope", "END_TO_END")
            page.click("#rcBtn")
            page.wait_for_timeout(1500)
            result = page.inner_text("#rcResult")
            assert "置信度" in result, f"未渲染推荐结果：{result[:160]!r}"
            assert "判断依据" in result, "缺少判断依据"
            assert "BPR" in result, "目标 60% + 端到端，应推荐 BPR"
            page.screenshot(path=str(out_dir / "interaction-recommend.png"), full_page=True)

        # 项目详情：四个页签 + 步骤状态可改
        def project_detail_tabs() -> None:
            goto("projects")
            page.click("#view tbody tr >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            assert "概览" in page.inner_text("#mBody"), "详情弹窗未渲染"
            for label, marker in [
                ("KPI 追踪", "指标"),
                ("工作流推进", "阶段1"),
                ("下一步", "下一步"),
            ]:
                page.click(f'#mBody .tabs button:has-text("{label}")')
                page.wait_for_timeout(300)
                assert marker in page.inner_text("#mBody"), f"{label} 页签内容为空"
            # 改一个步骤状态，后端应回算进度
            page.click('#mBody .tabs button:has-text("工作流推进")')
            page.wait_for_timeout(300)
            page.locator("#pd-wk select").first.select_option("IN_PROGRESS")
            page.wait_for_timeout(2000)
            assert "步骤状态已更新" in page.inner_text("#toast"), "步骤状态未成功提交"
            # 关掉弹窗后它不应因为后台请求返回而重新弹出来
            close_modal()
            page.wait_for_timeout(1200)
            assert not page.is_visible("#mask.show"), "关闭后弹窗又自己弹回来了"

        # 立项向导：匹配 → 立项 → 列表出现
        def project_wizard() -> None:
            goto("projects")
            page.click("text=+ 新建流程项目")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            page.click("#npRecBtn")
            page.wait_for_timeout(1600)
            result = page.inner_text("#npResult")
            assert "置信度" in result, f"未渲染推荐结果：{result[:160]!r}"

            page.fill("#npName", "自检用临时项目")
            page.fill("#npOwner", "自检员")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(2200)
            assert not page.is_visible("#mask.show"), "提交后弹窗未关闭，可能是接口报错"
            listing = page.inner_text("#view")
            assert "自检用临时项目" in listing, "新建的项目没有出现在列表里"

        # 工具箱：详情 + 按问题找工具（预设问题 + 自由输入各测一次）
        def toolbox() -> None:
            goto("toolbox")
            page.click("#view .tool >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(1000)  # 弹窗先显示骨架屏，等内容回填
            body = page.inner_text("#mBody")
            assert "标准操作步骤" in body, f"工具详情缺少步骤：{body[:120]!r}"
            assert "常见误用" in body, "工具详情缺少常见误用"
            close_modal()
            page.wait_for_timeout(400)

            page.click("#toolChips span >> nth=0")
            page.wait_for_timeout(1500)
            res = page.inner_text("#toolMatchResult")
            assert "匹配分" in res, f"预设问题未匹配到工具：{res[:160]!r}"

            page.fill("#toolQ", "跨部门互相推诿")
            page.click("#toolQBtn")
            page.wait_for_timeout(1500)
            res2 = page.inner_text("#toolMatchResult")
            assert "RACI" in res2, f"自由输入应匹配到 RACI：{res2[:200]!r}"

        # 设计器：打开节点编辑，改等待时间，指标应变化
        def designer_edit_node() -> None:
            goto("designer")
            before = page.inner_text("#view")
            assert "流程模型" in before
            page.click("#view .node >> nth=0")
            page.wait_for_selector("#mask.show")
            assert "编辑活动节点" in page.inner_text("#mTitle")
            page.fill("#edWait", "0")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1800)
            assert "指标已重算" in page.inner_text("#toast"), page.inner_text("#toast")
            page.click('#view .seg button:has-text("指标与建议")')
            page.wait_for_timeout(800)
            assert "流程周期效率" in page.inner_text("#view")
            page.screenshot(path=str(out_dir / "interaction-designer.png"), full_page=True)

        # 运营监控：KPI 明细 + 异常处理弹窗
        def monitor() -> None:
            goto("monitor")
            page.click('#view .seg button:has-text("概览")')
            page.wait_for_timeout(500)
            view = page.inner_text("#view")
            assert "流程健康度雷达" in view, "雷达图未渲染"
            assert "整体达成率趋势" in view, "整体趋势图未渲染"
            page.click('#view .seg button:has-text("KPI 明细")')
            page.wait_for_timeout(600)
            assert "KPI 明细" in page.inner_text("#view"), "KPI 明细未渲染"
            page.click('#view .seg button:has-text("异常台账")')
            page.wait_for_timeout(600)
            # 异常台账在最后一张表，行内才有「处理」按钮
            page.click('#view button:has-text("处理") >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            body = page.inner_text("#mBody")
            assert "根因分析" in body, f"异常弹窗内容缺失：{body[:120]!r}"
            close_modal()
            page.wait_for_timeout(400)

        # 知识库：打开条目（会写入查阅次数）+ 快速找工具
        def knowledge() -> None:
            goto("knowledge")
            page.click("#view .tool >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            assert "查阅" in page.inner_text("#mBody"), "知识条目详情未渲染"
            close_modal()
            page.wait_for_timeout(1400)

            page.fill("#kbQ", "跨部门互相推诿、权责不清")
            page.click("#kbQBtn")
            page.wait_for_timeout(1500)
            res = page.inner_text("#kbMatch")
            assert "推荐工具" in res, f"快速找工具未出结果：{res[:160]!r}"

        # 甘特图与里程碑
        def project_gantt() -> None:
            goto("projects")
            page.click("#view tbody tr >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(1000)
            page.click('#mBody .tabs button:has-text("甘特图")')
            page.wait_for_timeout(400)
            body = page.inner_text("#pd-gt")
            assert "里程碑" in body, f"甘特图缺少里程碑：{body[:120]!r}"
            bars = page.eval_on_selector_all("#pd-gt .gantt-bar", "els => els.length")
            assert bars >= 5, f"甘特图阶段条不足：{bars}"
            dias = page.eval_on_selector_all("#pd-gt .dia", "els => els.length")
            assert dias >= 5, f"里程碑菱形不足：{dias}"
            page.screenshot(path=str(out_dir / "interaction-gantt.png"), full_page=True)
            close_modal()

        # 新建流程（写入口）
        def process_create() -> None:
            goto("map")
            page.click("text=+ 新建流程")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            page.fill("#pfCode", "L3-E2E")
            page.fill("#pfName", "自检用临时流程")
            page.fill("#pfOwner", "自检员")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1500)
            assert "已创建" in page.inner_text("#toast"), page.inner_text("#toast")
            assert "自检用临时流程" in page.inner_text("#view"), "新建的流程没有出现在地图上"

        # 登记异常（写入口）
        def exception_create() -> None:
            goto("monitor")
            page.click("text=+ 登记异常")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(500)
            page.fill("#neTitle", "自检用临时异常")
            page.fill("#neOwner", "自检员")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1600)
            assert "已登记" in page.inner_text("#toast"), page.inner_text("#toast")
            assert "自检用临时异常" in page.inner_text("#view")

        # 退出登录
        def logout_check() -> None:
            page.click('.usr button:has-text("退出")')
            page.wait_for_timeout(600)
            assert page.is_visible("#loginMask"), "退出后应回到登录页"
            assert page.inner_text("#userName").strip() == "未登录"

        # 主题壳：切换后 data-theme 生效，Canvas 图表要跟着重绘
        def theme_switch() -> None:
            goto("monitor")
            page.select_option("#themeSel", "slate")
            page.wait_for_timeout(400)
            assert page.evaluate("document.documentElement.dataset.theme") == "slate"
            page.screenshot(path=str(out_dir / "theme-slate.png"), full_page=True)
            page.select_option("#themeSel", "default")
            page.wait_for_timeout(300)
            assert page.evaluate("document.documentElement.dataset.theme") == "default"

        # 驾驶舱入口：快捷链接、指标卡、阶段行都要真的能跳转
        def dashboard_entries() -> None:
            goto("dashboard")
            page.click('#view .quick-link:has-text("流程地图")')
            page.wait_for_timeout(700)
            assert page.inner_text("#pageTitle") == "企业流程地图"

            goto("dashboard")
            page.click("#view a.kpi.stat >> nth=0")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "流程项目组合"
            assert page.locator("#view select").nth(2).input_value() == "ACTIVE"

            goto("dashboard")
            page.click("#view a.stage-row >> nth=0")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "流程项目组合"
            assert page.locator("#view select").nth(1).input_value() == "1"

            goto("dashboard")
            page.click("#view a.kpi.stat >> nth=2")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "运营监控与KPI"
            assert "异常台账" in page.inner_text("#view")

        # 指标口径：页面上必须有可悬停的说明
        def metric_help() -> None:
            goto("dashboard")
            assert page.locator("#view .metric-help").count() > 0, "驾驶舱没有指标口径提示"
            tip = page.locator("#view .metric-help >> nth=0").get_attribute("data-tip")
            assert tip and len(tip) > 6, f"指标口径提示为空：{tip!r}"
            page.hover("#view .metric-help >> nth=0")
            page.wait_for_timeout(250)
            tooltip = page.evaluate(
                "() => { const s = getComputedStyle(document.querySelector('#view .metric-help'), '::after');"
                " return [s.visibility, s.opacity, s.content]; }"
            )
            assert tooltip[0] == "visible" and float(tooltip[1]) > 0, f"口径提示未显示：{tooltip}"

        # 流程执行：启动实例、认领任务、完成并推进
        def execution_flow() -> None:
            goto("execution")
            page.click("#execStartBtn")
            page.wait_for_selector("#exProcess")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1500)
            assert "流程已启动" in page.inner_text("#toast"), page.inner_text("#toast")

            row = page.locator("#view .exec-task-row").first
            iid = row.get_attribute("data-instance-id")
            try:
                assert iid, "任务行缺少 instance id"
                page.click("#view .exec-task-row >> nth=0 >> button")
                page.wait_for_timeout(900)
                assert "已认领" in page.inner_text("#toast"), page.inner_text("#toast")

                page.click("#view .exec-task-row >> nth=0 >> button")
                page.wait_for_selector("#exForm")
                page.click("#mFoot .btn-p")
                page.wait_for_timeout(1500)
                assert "任务已完成" in page.inner_text("#toast"), page.inner_text("#toast")
                assert "需求汇总与归并" in page.inner_text("#view"), "下一节点任务未生成"
            finally:
                if iid:
                    page.evaluate(
                        """async (iid) => {
                          const t = localStorage.getItem('psm_token');
                          await fetch('/api/v1/execution/instances/' + iid,
                            {method: 'DELETE', headers: {Authorization: 'Bearer ' + t}});
                        }""",
                        int(iid),
                    )

        check("地图下钻", map_drill)
        check("对标框架切换", benchmark_switch)
        check("主题切换", theme_switch)
        check("驾驶舱入口", dashboard_entries)
        check("指标口径提示", metric_help)
        check("工作流步骤详情", workflow_step_modal)
        check("方法论匹配引擎", workflow_recommend)
        check("项目详情四页签 + 步骤改状态", project_detail_tabs)
        check("立项向导（真实入库）", project_wizard)
        check("工具箱详情 + 按问题找工具", toolbox)
        check("设计器改节点并重算", designer_edit_node)
        check("监控异常处理弹窗", monitor)
        check("知识库详情 + 快速找工具", knowledge)
        check("项目甘特图与里程碑", project_gantt)
        check("新建流程架构", process_create)
        check("登记异常事件", exception_create)
        check("流程执行：启动→认领→完成", execution_flow)

        # -------------------------------------------------- 收尾：清理自检写入的数据
        def cleanup() -> None:
            """自检会真的调 POST 建数据，跑完要删掉，保证脚本可反复执行。"""
            script = """
              async () => {
                const t = localStorage.getItem('psm_token');
                const h = { Authorization: 'Bearer ' + t };
                const out = [];
                const proj = await fetch('/api/v1/projects?page_size=200', { headers: h }).then(r => r.json());
                for (const p of proj.items) {
                  if (p.name.includes('自检用')) {
                    await fetch('/api/v1/projects/' + p.id, { method: 'DELETE', headers: h });
                    out.push('project:' + p.code);
                  }
                }
                const procs = await fetch('/api/v1/process-map/flat', { headers: h }).then(r => r.json());
                for (const p of procs) {
                  if (p.code === 'L3-E2E') {
                    await fetch('/api/v1/process-map/' + p.id, { method: 'DELETE', headers: h });
                    out.push('process:' + p.code);
                  }
                }
                const exc = await fetch('/api/v1/monitor/exceptions?limit=500', { headers: h }).then(r => r.json());
                for (const e of exc) {
                  if (e.title.includes('自检用')) {
                    await fetch('/api/v1/monitor/exceptions/' + e.id, { method: 'DELETE', headers: h });
                    out.push('exception:' + e.code);
                  }
                }
                return out;
              }
            """
            removed = page.evaluate(script)
            if removed:
                print(f"NOTICE 已清理自检产生的 {len(removed)} 条数据：{', '.join(removed)}")

        check("清理自检数据", cleanup)
        check("退出登录回到登录页", logout_check)

        browser.close()

    # ---------------------------------------------------- 汇总
    print()
    if page_errors:
        print("!! 页面 JS 异常:")
        for e in page_errors:
            print("   -", e)
    if failed_requests:
        print("!! 失败请求:")
        for r in dict.fromkeys(failed_requests):
            print("   -", r)
    if console_errors:
        print("!! 控制台 error:")
        for c in dict.fromkeys(console_errors):
            print("   -", c)
    if not (page_errors or failed_requests or console_errors):
        print("未发现 JS 异常与失败请求。")
    print(f"截图已写入 {out_dir.resolve()}")

    if failures:
        print(f"\n失败项：{', '.join(failures)}")
        return 1
    print("\n全部检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
