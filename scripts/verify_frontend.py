"""前端联调自检。

两段：
  1. 视图渲染 —— 各业务视图逐个点一遍，收集 JS 报错与失败请求，并截图
  2. 交互路径 —— 驱动关键交互（模态框、页签、表单提交、下钻），断言真实渲染结果

用法：
    python scripts/verify_frontend.py [http://127.0.0.1:8123] [截图输出目录]
"""

from __future__ import annotations

import sys
import tempfile
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
    ("deliverables", "交付物与模板库"),
    ("orgs", "组织与人员"),
    ("sketches", "架构草图"),
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
        page = browser.new_page(viewport={"width": 1440, "height": 950}, accept_downloads=True)

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

        # 流程详情里的配套文件入口：L4 叶子节点 → 管理标准文件
        def map_documents_entry() -> None:
            goto("map")
            page.click('.crumb a:has-text("全部价值链")')
            page.wait_for_timeout(500)
            page.click("#view tr.map-row >> nth=2")
            page.wait_for_timeout(600)
            page.click("#view tr.map-row:has-text('L2-003')")
            page.wait_for_timeout(600)
            page.click("#view tr.map-row:has-text('L3-032')")
            page.wait_for_timeout(600)
            page.click("#view tr.map-row:has-text('L4-201')")
            page.wait_for_selector("#mask.show")
            page.wait_for_selector("#mapDocs h3", timeout=8000)
            body = page.inner_text("#mBody")
            assert "配套文件（标准）" in body, f"流程详情缺少配套文件区域：{body[:200]!r}"
            assert "还没有标准文件" in body, "无标准文件时应显示空态"
            page.click('#mBody button:has-text("管理配套文件")')
            page.wait_for_timeout(1500)
            assert page.inner_text("#pageTitle") == "交付物与模板库"
            selected = page.eval_on_selector(
                "#view select.sel", "el => el.options[el.selectedIndex].textContent"
            )
            assert "L4-201" in selected, f"管理入口未带入流程：{selected}"

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
            page.wait_for_selector("#wfRec h3", timeout=8000)
            body = page.inner_text("#mBody")
            assert "标准动作" in body and "关键要点" in body, body[:120]
            assert "推荐工具与预制模板" in body, "步骤弹窗缺少推荐工具区域"
            assert "该步骤还没有配置工具" in body, "1.1 没有配置工具，应给出提示"
            close_modal()
            page.wait_for_timeout(300)

        # 步骤页推荐工具与模板：阶段 2 的 2.1 应有 SIPOC（必用）
        def workflow_step_recommendations() -> None:
            goto("workflow")
            page.click('#view .stage-pill:has-text("阶段2")')
            page.wait_for_timeout(500)
            page.click('#view .wf-step:has-text("现状流程绘制")')
            page.wait_for_selector("#wfRec table", timeout=8000)
            body = page.inner_text("#wfRec")
            assert "SIPOC" in body and "必用" in body, f"推荐工具未渲染：{body[:200]!r}"
            assert "SWIMLANE" in body and "推荐" in body
            assert "暂无预制模板" in body, "未上传模板时应显示空态"
            close_modal()

        # 步骤页 → 工具箱：只展示本步骤推荐工具，并标注使用要求
        def step_to_filtered_toolbox() -> None:
            goto("workflow")
            page.click('#view .stage-pill:has-text("阶段2")')
            page.wait_for_timeout(500)
            page.click('#view .wf-step:has-text("现状流程绘制")')
            page.wait_for_selector("#wfRec table", timeout=8000)
            page.click('#mFoot button:has-text("只看本步骤")')
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "方法论工具箱"
            text = page.inner_text("#view")
            assert "只显示" in text and "现状流程绘制" in text, text[:200]
            assert "必用" in text and "推荐" in text, "工具使用要求标签未渲染"
            names = page.eval_on_selector_all(
                "#view .tool h4", "els => els.map(e => e.textContent.trim())"
            )
            assert len(names) == 2, f"过滤后应只有 2 个工具：{names}"
            assert any("SIPOC" in n for n in names) and any(
                "Swimlane" in n or "泳道" in n for n in names
            )

            page.click('#view button:has-text("显示全部工具")')
            page.wait_for_timeout(900)
            names_all = page.eval_on_selector_all(
                "#view .tool h4", "els => els.map(e => e.textContent.trim())"
            )
            assert len(names_all) > 2, f"清除过滤后应显示更多工具：{names_all}"

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

        # 交付物与模板库：项目交付物列表 → 详情弹窗 → 模板库空态/新建入口
        def deliverables_view() -> None:
            goto("deliverables")
            # 其他检查可能把页签停在标准文件；先切回项目交付物
            page.click('#view .tabs button:has-text("项目交付物")')
            page.wait_for_timeout(600)
            page.wait_for_selector("#dlvSummary .kpi", timeout=8000)
            text = page.inner_text("#view")
            assert "交付物总数" in text and "已生效" in text, text[:160]
            assert page.locator("#dlvList tbody tr").count() > 0, "项目交付物表为空"

            page.click('#dlvList button:has-text("详情") >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(600)
            body = page.inner_text("#mBody")
            assert "版本" in body and "验收口径" in body, f"交付物详情渲染异常：{body[:160]!r}"
            close_modal()

            page.click('#view .tabs button:has-text("流程标准文件")')
            page.wait_for_timeout(900)
            assert "还没有标准文件" in page.inner_text("#view"), "标准文件空态未渲染"
            assert "全部组织" in page.inner_text("#view"), "标准文件缺少组织筛选"
            assert "集团总部" in page.inner_text("#view"), "组织下拉未加载"
            page.click('#view button:has-text("新建标准文件")')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "所属流程" in body, "新建标准文件弹窗缺少流程选择"
            assert "适用范围" in body and "集团总部" in body, "新建标准文件缺少组织范围"
            assert "变体策略" in body and "依据上级标准" in body, "新建标准文件缺少变体配置"
            close_modal()

            # 选择组织后应出现有效版本解析（当前无标准文件 → 空态）
            page.locator("#view select.sel").nth(2).select_option(label="华东分公司（公司/分公司）")
            page.wait_for_timeout(1200)
            assert "该组织在所选范围内没有可用标准文件" in page.inner_text("#view")

            page.click('#view .tabs button:has-text("工具模板库")')
            page.wait_for_timeout(900)
            assert "模板库还没有模板" in page.inner_text("#view"), "模板库空态未渲染"
            page.click('#view button:has-text("新建模板")')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "归属工具" in body, "新建模板弹窗缺少工具选择"
            assert "适用范围" in body, "新建模板弹窗缺少组织范围"
            close_modal()

            page.click('#view .tabs button:has-text("基线与审计")')
            page.wait_for_timeout(900)
            assert "还没有基线" in page.inner_text("#view"), "基线空态未渲染"
            assert "治理概览" in page.inner_text("#view"), "治理概览未渲染"
            assert "落后变体" in page.inner_text("#view")
            assert "没有待处理的治理问题" in page.inner_text("#view"), "治理待办空态未渲染"
            assert "运行审计" in page.inner_text("#view"), "缺少运行审计入口"
            page.click('#view button:has-text("创建基线")')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "名称" in body and "范围" in body, "创建基线弹窗字段缺失"
            close_modal()

        def deliverables_upload() -> None:
            project_id = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const r = await fetch('/api/v1/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json',
                               Authorization: 'Bearer ' + t },
                    body: JSON.stringify({ name: '自检用交付物项目', methodology: 'BPI',
                      owner: '自检员', start_date: '2026-10-01', end_date: '2027-03-31' })
                  });
                  return (await r.json()).id;
                }"""
            )
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.write(b"PK\x03\x04" + b"e2e deliverable upload")
            tmp.close()
            try:
                goto("deliverables")
                # 上一项检查停在模板页签；先切回项目交付物，再选项目
                page.click('#view .tabs button:has-text("项目交付物")')
                page.wait_for_timeout(800)
                page.select_option("#view select.sel", str(project_id))
                page.wait_for_timeout(1200)
                page.click('#dlvList button:has-text("上传") >> nth=0')
                page.wait_for_selector("#dvFile")
                page.set_input_files("#dvFile", tmp.name)
                page.fill("#dvTitle", "自检上传件")
                page.click("#mFoot .btn-p")
                page.wait_for_timeout(2000)
                assert "已上传" in page.inner_text("#toast"), page.inner_text("#toast")
                assert "R1" in page.inner_text("#dlvList"), "上传后列表未显示 R1"
            finally:
                page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/projects/' + pid,
                        { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } });
                    }""",
                    int(project_id),
                )
                Path(tmp.name).unlink(missing_ok=True)

        # 组织与人员：只读检查组织树、人员列表与新建入口
        def admin_orgs() -> None:
            goto("orgs")
            page.wait_for_selector("#adminBody table", timeout=8000)
            text = page.inner_text("#view")
            assert "组织架构" in text and "集团总部" in text, text[:200]
            page.click('#view .tabs button:has-text("人员与角色")')
            page.wait_for_timeout(600)
            text = page.inner_text("#view")
            assert "人员与角色" in text and "系统管理员" in text, text[:200]
            page.click('#view button:has-text("新建人员")')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "用户名" in body and "归属组织" in body, body[:160]
            close_modal()
            page.click('#view .tabs button:has-text("组织架构")')
            page.wait_for_timeout(400)
            page.click('#view button:has-text("新建组织")')
            page.wait_for_selector("#mask.show")
            assert "组织编码" in page.inner_text("#mBody")
            close_modal()

        # 架构树计数：L1「研发设计」下含 9 个 L4 活动
        def map_tree_counts() -> None:
            goto("map")
            page.click('.crumb a:has-text("全部价值链")')
            page.wait_for_timeout(600)
            item = page.locator("#view .tree-item").filter(has_text="研发设计").first
            count = item.locator(".cnt")
            assert count.inner_text().strip() == "9", (
                f"L1 研发设计 L4 活动数错误：{count.inner_text()}"
            )
            assert "含 9 个 L4 活动" in (count.get_attribute("data-tip") or "")
            assert count.get_attribute("title") is None, "计数不应再使用浏览器原生 title 提示"

        # 设计器：打开节点编辑，改等待时间，指标应变化
        def designer_edit_node() -> None:
            goto("designer")
            if page.locator('#view button:has-text("简洁画布")').count():
                page.click('#view button:has-text("简洁画布")')
                page.wait_for_timeout(400)
            before = page.inner_text("#view")
            assert "流程模型" in before
            page.wait_for_selector("#designerCanvas")
            assert page.locator("#view .designer-node").count() >= 6, "画布没有渲染节点"
            assert page.locator("#view .designer-edge").count() >= 5, "画布没有渲染连线"
            edge_point = page.locator("#view .designer-edge-hit").first.evaluate(
                """el => {
                  const p = el.getPointAtLength(el.getTotalLength() / 2);
                  const pt = new DOMPoint(p.x, p.y).matrixTransform(el.getScreenCTM());
                  return { x: pt.x, y: pt.y };
                }"""
            )
            page.mouse.click(edge_point["x"], edge_point["y"])
            page.wait_for_selector("#mask.show")
            assert "编辑连线" in page.inner_text("#mTitle")
            page.click('#mFoot button:has-text("取消")')
            page.wait_for_timeout(300)
            page.click("#view .node >> nth=0")
            page.wait_for_selector("#mask.show")
            assert "编辑活动节点" in page.inner_text("#mTitle")
            original_wait = page.input_value("#edWait")
            page.fill("#edWait", "0")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1800)
            assert "指标已重算" in page.inner_text("#toast"), page.inner_text("#toast")

            # 还原演示数据，避免自检反复改写种子模型
            page.click("#view .node >> nth=0")
            page.wait_for_selector("#mask.show")
            page.fill("#edWait", original_wait)
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1500)
            page.click('#view .seg button:has-text("指标与建议")')
            page.wait_for_timeout(800)
            assert "流程周期效率" in page.inner_text("#view")
            page.screenshot(path=str(out_dir / "interaction-designer.png"), full_page=True)

        # 专业 BPMN 画布（bpmn-js）：加载、调色板、水印、返回简洁画布
        def designer_bpmn_spike() -> None:
            goto("designer")
            if page.locator('#view .seg button:has-text("流程模型")').count():
                page.click('#view .seg button:has-text("流程模型")')
                page.wait_for_timeout(300)
            if page.locator('#view button:has-text("专业 BPMN 画布")').count():
                page.click('#view button:has-text("专业 BPMN 画布")')
            page.wait_for_selector("#bpmnCanvas .djs-palette", timeout=8000)
            page.wait_for_selector("#bpmnCanvas .djs-element", timeout=8000)
            assert page.locator("#bpmnCanvas .djs-element").count() >= 5
            assert page.locator(".bjs-powered-by").count() == 1, "bpmn.io 水印必须保留"
            page.click('#view button:has-text("运行校验")')
            page.wait_for_selector(".bpmn-lint-item", timeout=8000)
            assert page.locator(".bpmn-lint-item").count() >= 1
            page.click('#view button:has-text("全屏")')
            page.wait_for_timeout(400)
            assert page.locator("#bpmnCard").evaluate("e => e.classList.contains('fullscreen')")
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            assert not page.locator("#bpmnCard").evaluate("e => e.classList.contains('fullscreen')")
            page.click('#view button:has-text("简洁画布")')
            page.wait_for_selector("#designerCanvas")
            page.screenshot(path=str(out_dir / "interaction-designer-bpmnjs.png"), full_page=True)

        # 设计器：草稿 → 评审 → 发布，版本历史可打开
        def designer_version_governance() -> None:
            created = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const code = 'L3-VER-' + Math.random().toString(36).slice(2, 6).toUpperCase();
                  const r = await fetch('/api/v1/process-map', {
                    method: 'POST',
                    headers: { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' },
                    body: JSON.stringify({ code, name: '版本治理自检', level: 3 })
                  });
                  return await r.json();
                }"""
            )
            pid = created["id"]
            fallback = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const rows = await fetch('/api/v1/process-map/flat',
                    { headers: { Authorization: 'Bearer ' + t } }).then(r => r.json());
                  return rows.find(r => r.code === 'L3-032').id;
                }"""
            )
            try:
                page.evaluate(f"switchProcess({pid})")
                page.wait_for_timeout(500)
                if page.locator('#view button:has-text("简洁画布")').count():
                    page.click('#view button:has-text("简洁画布")')
                    page.wait_for_timeout(300)
                if page.locator('#view .seg button:has-text("流程模型")').count():
                    page.click('#view .seg button:has-text("流程模型")')
                page.wait_for_selector("#designerCanvas")
                page.wait_for_timeout(500)
                for label in ("开始", "作业", "结束"):
                    page.click(f'#view .designer-toolbar button:has-text("{label}")')
                    page.wait_for_timeout(700)
                assert "草稿" in page.inner_text("#view"), page.inner_text("#view")[:200]

                # 节点级执行配置：设计器内直接设时限
                page.click("#view .designer-node >> nth=0")
                page.wait_for_selector("#edDue")
                assert "执行配置" in page.inner_text("#mBody")
                page.fill("#edDue", "2")
                page.click('#mBody button:has-text("保存执行配置")')
                page.wait_for_timeout(700)
                assert "节点执行配置已保存" in page.inner_text("#toast")
                page.click('#mFoot button:has-text("取消")')

                page.click('#view button:has-text("版本历史")')
                page.wait_for_selector("#mask.show")
                assert "模型版本历史" in page.inner_text("#mTitle")
                assert "草稿" in page.inner_text("#mBody")
                close_modal()

                page.once("dialog", lambda dialog: dialog.accept("E2E 评审"))
                page.click('#view button:has-text("提交评审")')
                page.wait_for_timeout(1400)
                assert "待评审" in page.inner_text("#view"), page.inner_text("#view")[:200]

                page.once("dialog", lambda dialog: dialog.accept())
                page.click('#view button:has-text("发布到运行时")')
                page.wait_for_timeout(1600)
                view_text = page.inner_text("#view")
                assert "已发布" in view_text and "运行时版本 v" in view_text, view_text[:200]
                page.screenshot(
                    path=str(out_dir / "interaction-designer-version.png"), full_page=True
                )
            finally:
                page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/process-map/' + pid,
                        { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } });
                    }""",
                    pid,
                )
                page.evaluate(f"switchProcess({fallback})")
                page.wait_for_timeout(700)

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

        # 直接打开视图路径：服务端返回前端入口，启动后按路径进入对应视图
        def direct_view_url() -> None:
            page.goto(base + "/orgs", wait_until="networkidle")
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "组织与人员", (
                f"直接打开 /orgs 未进入组织页面：{page.inner_text('#pageTitle')}"
            )
            goto("dashboard")

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
            page.click('#view .mainline-step:has-text("流程地图")')
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
            page.click("#view .card:has(h3:has-text('改善优先级')) tbody tr >> nth=0")
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "企业流程地图"
            page.wait_for_selector("#mask.show")
            assert "综合优先级得分" in page.inner_text("#mask")
            close_modal()

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
            assert page.locator("#view .metric-help >> nth=0").get_attribute("title") is None, (
                "原生 title 会与自定义提示重复弹出"
            )
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
            page.wait_for_selector("#exAssign select", timeout=8000)
            assert "节点处理人" in page.inner_text("#mBody"), "启动弹窗缺少节点处理人配置"
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1500)
            assert "流程已启动" in page.inner_text("#toast"), page.inner_text("#toast")

            row = page.locator("#view .exec-task-row").first
            iid = row.get_attribute("data-instance-id")
            try:
                assert iid, "任务行缺少 instance id"

                # 挂起 / 恢复：挂起后任务操作应被阻断
                page.click('#view .seg button:has-text("流程实例")')
                page.wait_for_timeout(600)
                inst_row = page.locator(f'#view tr.exec-instance-row[data-instance-id="{iid}"]')
                inst_row.locator('button:has-text("详情")').click()
                page.wait_for_selector('#mFoot button:has-text("挂起实例")')
                page.once("dialog", lambda dialog: dialog.accept("E2E 挂起"))
                page.click('#mFoot button:has-text("挂起实例")')
                page.wait_for_timeout(900)
                assert "已挂起" in page.inner_text("#toast"), page.inner_text("#toast")

                inst_row = page.locator(f'#view tr.exec-instance-row[data-instance-id="{iid}"]')
                inst_row.locator('button:has-text("详情")').click()
                page.wait_for_selector('#mFoot button:has-text("恢复实例")')
                assert "已挂起" in page.inner_text("#mBody")
                page.click('#mFoot button:has-text("恢复实例")')
                page.wait_for_timeout(900)
                assert "已恢复" in page.inner_text("#toast"), page.inner_text("#toast")

                page.click('#view .seg button:has-text("待办任务")')
                page.wait_for_timeout(600)
                page.click("#view .exec-task-row >> nth=0 >> button")
                page.wait_for_timeout(900)
                assert "已认领" in page.inner_text("#toast"), page.inner_text("#toast")

                page.click("#view .exec-task-row >> nth=0 >> button")
                page.wait_for_selector("#exf_applicant")
                assert "任务历史" in page.inner_text("#mBody"), "任务弹窗缺少任务历史"
                page.fill("#exf_applicant", "自检用户")
                page.fill("#exf_amount", "1000")
                page.click("#mFoot .btn-p")
                page.wait_for_timeout(1500)
                assert "任务已完成" in page.inner_text("#toast"), page.inner_text("#toast")
                assert "需求汇总与归并" in page.inner_text("#view"), "下一节点任务未生成"

                page.click('#view .seg button:has-text("表单与规则")')
                page.wait_for_timeout(1000)
                config_text = page.inner_text("#view")
                assert "任务时限与升级" in config_text and page.locator("#exDueHours").count() == 1
                assert page.locator("#exEscHours").count() == 1
                assert page.locator("#exEscUser").count() == 1
                assert "运行升级扫描" in config_text
                assert "节点分派" in config_text, "执行配置缺少节点分派"
                assert "表单定义" in config_text and "需求发起" in config_text
                assert "分支规则" in config_text and "审批通过" in config_text

                # 节点分派弹窗：角色 / 组织 / 默认处理人 / 节点时限 / 升级
                page.locator("#view .card", has_text="节点分派").locator(
                    "button:has-text('配置')"
                ).first.click()
                page.wait_for_selector("#naRole")
                modal_text = page.inner_text("#mBody")
                assert "候选角色" in modal_text and "限定组织" in modal_text
                assert "默认处理人" in modal_text and "节点时限" in modal_text
                assert "升级时限" in modal_text and "升级处理人" in modal_text
                page.click("#mFoot .btn-g")
                page.wait_for_timeout(300)

                page.click('#view .seg button:has-text("集成")')
                page.wait_for_timeout(1000)
                integration_text = page.inner_text("#view")
                assert "集成端点" in integration_text and "ERP 事件接收" in integration_text
                assert "入站 Webhook" in integration_text, "集成页缺少入站 Webhook"
                page.click('#view button:has-text("+ 新建入站")')
                page.wait_for_selector("#ihCode")
                inbound_text = page.inner_text("#mBody")
                assert "服务账号" in inbound_text and "允许动作" in inbound_text
                page.click("#mFoot .btn-g")
                page.wait_for_timeout(300)
                page.click('#view button:has-text("运行待发送")')
                page.wait_for_timeout(800)
                assert "没有待发送" in page.inner_text("#toast"), page.inner_text("#toast")
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

        # 分支规则：自动模式不传 next_node_key，应由规则路由到 n5
        def branch_mode_rule() -> None:
            iid = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const h = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
                  const procs = await fetch('/api/v1/execution/processes', { headers: h })
                    .then(r => r.json());
                  const p = procs.find(x => x.code === 'L3-032');
                  const inst = await fetch('/api/v1/execution/instances', {
                    method: 'POST', headers: h, body: JSON.stringify({ process_id: p.id })
                  }).then(r => r.json());
                  const open = async () => (await fetch(
                    '/api/v1/execution/tasks?instance_id=' + inst.id + '&only_open=true',
                    { headers: h }).then(r => r.json()))[0];
                  let task = await open();
                  await fetch('/api/v1/execution/tasks/' + task.id + '/complete', {
                    method: 'POST', headers: h,
                    body: JSON.stringify({ form_data: { applicant: '分支测试', amount: 100 } })
                  });
                  for (let i = 0; i < 2; i++) {
                    task = await open();
                    await fetch('/api/v1/execution/tasks/' + task.id + '/complete', {
                      method: 'POST', headers: h, body: JSON.stringify({})
                    });
                  }
                  task = await open();
                  await fetch('/api/v1/execution/tasks/' + task.id + '/claim', {
                    method: 'POST', headers: h, body: '{}'
                  });
                  return inst.id;
                }"""
            )
            try:
                goto("execution")
                page.click('#view button:has-text("待办任务")')
                page.wait_for_timeout(400)
                page.click('#view button:has-text("全部待办")')
                page.wait_for_timeout(600)
                row = page.locator(f'#view tr.exec-task-row[data-instance-id="{iid}"]')
                row.locator('button:has-text("处理")').first.click()
                page.wait_for_selector("#exBranchMode")
                assert page.locator("#exBranchMode").input_value() == "auto"
                assert page.locator("#exNextWrap").evaluate("el => el.classList.contains('hide')")
                page.select_option("#exf_approved", "是")
                page.click("#mFoot .btn-p")
                page.wait_for_timeout(1500)
                assert "任务已完成" in page.inner_text("#toast"), page.inner_text("#toast")
                next_node = page.evaluate(
                    """async (iid) => {
                      const t = localStorage.getItem('psm_token');
                      const h = { Authorization: 'Bearer ' + t };
                      const rows = await fetch(
                        '/api/v1/execution/tasks?instance_id=' + iid + '&only_open=true',
                        { headers: h }).then(r => r.json());
                      return rows.length ? rows[0].node_key : null;
                    }""",
                    iid,
                )
                assert next_node == "n5", f"规则未自动路由到 n5：{next_node}"
            finally:
                page.evaluate(
                    """async (iid) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/execution/instances/' + iid,
                        { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } });
                    }""",
                    iid,
                )

        # BPMN 导出后再导入，结构应保持不变
        def bpmn_roundtrip() -> None:
            goto("designer")
            if page.locator("#view .page-head select.sel").count():
                page.select_option("#view .page-head select.sel", label="L3 L3-032 采购需求提报")
                page.wait_for_timeout(900)
            tmp = tempfile.NamedTemporaryFile(suffix=".bpmn", delete=False)
            tmp.close()
            path = Path(tmp.name)
            try:
                with page.expect_download() as download_info:
                    page.click('#view button:has-text("导出 BPMN")')
                download_info.value.save_as(str(path))
                xml = path.read_text(encoding="utf-8")
                assert "<bpmn:process" in xml, "导出的文件不是 BPMN XML"
                assert 'id="n1"' in xml

                with page.expect_file_chooser() as chooser_info:
                    page.click('#view button:has-text("导入 BPMN")')
                chooser_info.value.set_files(str(path))
                page.wait_for_timeout(1800)
                assert "BPMN 已导入" in page.inner_text("#toast"), page.inner_text("#toast")
                assert "采购需求提报" in page.inner_text("#view")
            finally:
                path.unlink(missing_ok=True)

        # 通知中心：未读徽标与通知列表
        def notifications() -> None:
            goto("dashboard")
            badge = page.locator("#notifBadge")
            assert badge.count() == 1
            page.click("#notifBtn")
            page.wait_for_selector(".notif-list")
            assert "通知中心" in page.inner_text("#mTitle")
            body = page.inner_text("#mBody")
            # 演示库可能已经被读过，通知中心仍应能打开并展示列表/空态
            assert any(marker in body for marker in ("欢迎使用", "暂无", "条未读", "全部已读")), (
                body[:120]
            )
            mark_all = page.locator("#mBody button:has-text('全部已读')")
            if mark_all.count():
                mark_all.first.click()
                page.wait_for_timeout(400)
            close_modal()

        # 地图 → 立项：带流程进入项目向导
        def map_to_project() -> None:
            goto("map")
            page.click('.crumb a:has-text("全部价值链")')
            page.wait_for_timeout(500)
            page.click("#view tr.map-row >> nth=2")
            page.wait_for_timeout(600)
            page.click("#view tr.map-row:has-text('L2-003')")
            page.wait_for_timeout(600)
            row = page.locator("#view tr.map-row:has-text('L3-032')").first
            row.locator("a.link:has-text('立项')").click()
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "流程项目组合"
            page.wait_for_selector("#npName")
            assert "从流程地图带入" in page.inner_text("#mBody")
            selected = page.eval_on_selector(
                "#npProcess", "el => el.options[el.selectedIndex].textContent"
            )
            assert "L3-032" in selected, selected
            close_modal()

        check("地图下钻", map_drill)
        check("架构树计数", map_tree_counts)
        check("流程详情配套文件入口", map_documents_entry)
        check("对标框架切换", benchmark_switch)
        check("主题切换", theme_switch)
        check("驾驶舱入口", dashboard_entries)
        check("指标口径提示", metric_help)
        check("通知中心", notifications)
        check("工作流步骤详情", workflow_step_modal)
        check("步骤推荐工具与模板", workflow_step_recommendations)
        check("步骤页过滤工具箱", step_to_filtered_toolbox)
        check("方法论匹配引擎", workflow_recommend)
        check("项目详情四页签 + 步骤改状态", project_detail_tabs)
        check("立项向导（真实入库）", project_wizard)
        check("工具箱详情 + 按问题找工具", toolbox)
        check("交付物与模板库", deliverables_view)
        check("交付物上传（真实入库）", deliverables_upload)
        check("组织与人员管理界面", admin_orgs)
        check("设计器改节点并重算", designer_edit_node)
        check("设计器专业 BPMN 画布（bpmn-js）", designer_bpmn_spike)
        check("设计器版本治理（草稿→评审→发布）", designer_version_governance)
        check("监控异常处理弹窗", monitor)
        check("知识库详情 + 快速找工具", knowledge)
        check("项目甘特图与里程碑", project_gantt)
        check("新建流程架构", process_create)
        check("登记异常事件", exception_create)
        check("流程执行：启动→认领→完成", execution_flow)
        check("流程执行：分支规则自动路由", branch_mode_rule)
        check("地图→立项", map_to_project)
        check("BPMN 导入导出", bpmn_roundtrip)

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
        check("直接打开视图路径", direct_view_url)
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
