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
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

# Windows 控制台默认是 GBK，中文输出会变乱码
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VIEWS = [
    ("dashboard", "运营驾驶舱"),
    ("start", "开始使用"),
    ("strategy", "战略目标"),
    ("map", "企业流程地图"),
    ("process_card", "流程卡"),
    ("authorization", "授权矩阵"),
    ("pilot", "十层核对"),
    ("workflow", "五阶段标准工作流"),
    ("projects", "流程项目组合"),
    ("toolbox", "方法论工具箱"),
    ("designer", "流程设计器"),
    ("monitor", "运营驾驶舱"),
    ("data", "数据治理"),
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

        skipped_keys: list[str] = []

        # 侧栏按两件事分组，入口都露在外面。流程卡、五阶段、工具箱、交付物从页面里进入。
        def default_entry_and_nav() -> None:
            assert page.inner_text("#pageTitle") == "开始使用", (
                f"默认落地页应固定为「开始使用」，实际「{page.inner_text('#pageTitle')}」"
            )
            groups = [text.strip() for text in page.locator(".nav .grp").all_inner_texts()]
            assert groups == ["把公司流程体系立起来", "把一条流程改好"], groups
            assert page.locator("#expertToggle").count() == 0
            assert page.locator('.nav a[data-view="map"]').is_visible()
            assert page.locator('.nav a[data-view="execution"]').is_visible()
            assert page.locator('.nav a[data-view="workflow"]').count() == 0
            assert page.locator('.nav a[data-view="pcf"]').count() == 0

        check("默认入口与两侧栏分组", default_entry_and_nav)

        # ---------------------------------------------------- 第一段：视图渲染
        print("── 视图渲染 ──")
        for view, _title in VIEWS:
            if view == "monitor":
                # 合并后侧栏只有一个「运营驾驶舱」，monitor 从 KPI 页签进入
                page.evaluate("() => go('monitor', {params: {tab: 'kpi'}, skipOrigin: true})")
            elif page.locator(f'.nav a[data-view="{view}"]').count() == 0:
                # 流程卡、五阶段、工具箱、交付物、PCF、草图、数据治理不占侧栏
                page.evaluate(f"() => go('{view}', {{skipOrigin: true}})")
            else:
                page.click(f'.nav a[data-view="{view}"]')
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(600)
            if view == "dashboard":
                try:
                    page.wait_for_selector("#view .kpi.stat", timeout=8000)
                except Exception:
                    pass
            if view == "process_card":
                # 流程卡要先拉流程清单、再拉详情，两次串行请求，给足时间
                try:
                    page.wait_for_selector("#view select.sel", timeout=8000)
                except Exception:
                    pass

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
            page.evaluate("() => { for (let i = 0; i < 8; i += 1) window.closeModal(); }")
            page.wait_for_timeout(200)

        def goto(view: str) -> None:
            # 上一个检查可能留下未关的弹窗/全屏画布，遮罩会挡住导航点击
            page.keyboard.press("Escape")
            # 弹窗可能是嵌套栈，重复关闭直到栈清空（window 只暴露 closeModal）
            page.evaluate("() => { for (let i = 0; i < 8; i += 1) window.closeModal(); }")
            page.wait_for_timeout(150)
            page.click(f'.nav a[data-view="{view}"]')
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(600)

        def goto_workflow_tab(label: str) -> None:
            """workflow 默认落在项目工作台，方法手册相关检查要先切页签。"""
            goto("workflow")
            page.click(f'#view .wb-tabs button:has-text("{label}")')
            page.wait_for_timeout(600)

        def goto_cockpit_tab(label: str) -> None:
            """运营驾驶舱只有一个侧栏入口，其余页签从总览切。"""
            goto("dashboard")
            page.click(f'#view .cockpit-tabs button:has-text("{label}")')
            page.wait_for_timeout(900)

        def pick_editable_design() -> None:
            """选一条可编辑、节点足够且含 n3 的流程，避免本地数据进入评审后自检失效。"""
            picked = None
            for _attempt in range(4):
                picked = page.evaluate(
                    """async () => {
                      const t = localStorage.getItem('psm_token');
                      const rows = await fetch('/api/v1/process-map/flat', {
                        headers: {'Authorization': 'Bearer ' + t},
                      }).then(r => r.json());
                      for (const row of rows) {
                        if (row.level < 3) continue;
                        const res = await fetch('/api/v1/processes/' + row.id + '/design', {
                          headers: {'Authorization': 'Bearer ' + t},
                        });
                        if (!res.ok) continue;
                        const model = await res.json();
                        const keys = (model.nodes || []).map(n => n.node_key);
                        if (model.status !== 'IN_REVIEW'
                            && keys.includes('n3') && keys.length >= 6) {
                          return {id: row.id, code: row.code};
                        }
                      }
                      return null;
                    }"""
                )
                if picked:
                    break
                page.wait_for_timeout(700)
            assert picked, "没有可编辑的演示流程（需要非评审、至少 6 个节点且含 n3）"
            page.select_option("#view select.sel", value=str(picked["id"]))

        def select_bpmn_node(key: str) -> None:
            """自动布局下连线命中区可能压过节点，用 bpmn-js 选择 API 稳定选中。"""
            page.evaluate(
                """(key) => {
                  const modeler = window.__bpmnSpike.modeler;
                  modeler.get('selection').select(
                    modeler.get('elementRegistry').get(key));
                }""",
                key,
            )
            page.wait_for_timeout(300)

        def start_bpmn_direct_editing(key: str) -> None:
            page.evaluate(
                """(key) => {
                  const modeler = window.__bpmnSpike.modeler;
                  modeler.get('directEditing').activate(
                    modeler.get('elementRegistry').get(key));
                }""",
                key,
            )
            page.wait_for_timeout(300)
            page.wait_for_timeout(1500)

        def pick_review_design() -> dict | None:
            """找一条评审中的流程，用于验证只读状态下调色板仍可见。"""
            picked = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const rows = await fetch('/api/v1/process-map/flat', {
                    headers: {'Authorization': 'Bearer ' + t},
                  }).then(r => r.json());
                  for (const row of rows) {
                    if (row.level < 3) continue;
                    const res = await fetch('/api/v1/processes/' + row.id + '/design', {
                      headers: {'Authorization': 'Bearer ' + t},
                    });
                    if (!res.ok) continue;
                    const model = await res.json();
                    if (model.status === 'IN_REVIEW' && (model.nodes || []).length) {
                      return {id: row.id, code: row.code};
                    }
                  }
                  return null;
                }"""
            )
            if picked:
                page.select_option("#view select.sel", value=str(picked["id"]))
                page.wait_for_timeout(1500)
            return picked

        # 地图下钻
        def map_drill() -> None:
            goto("map")
            before = page.inner_text(".crumb")
            page.click("#view .map-open >> nth=2")
            page.wait_for_timeout(700)
            after = page.inner_text(".crumb")
            assert len(after) > len(before), f"面包屑未增长：{before!r} → {after!r}"
            assert page.inner_text("#view").count("Owner:") > 0

        def map_enter_button() -> None:
            goto("map")
            before = page.inner_text(".crumb")
            page.click('#view .map-go-btn:has-text("进入") >> nth=0')
            page.wait_for_timeout(700)
            after = page.inner_text(".crumb")
            assert len(after) > len(before), f"「进入」按钮没有下钻：{before!r} → {after!r}"

        # 流程详情里的配套文件入口：L4 叶子节点 → 管理标准文件
        def map_documents_entry() -> None:
            goto("map")
            page.click('.crumb a:has-text("全部价值链")')
            page.wait_for_timeout(500)
            page.click("#view .map-open >> nth=2")
            page.wait_for_timeout(600)
            page.click("#view .map-row:has-text('L2-003') .map-open")
            page.wait_for_timeout(600)
            page.click("#view .map-row:has-text('L3-032') .map-open")
            page.wait_for_timeout(600)
            page.click("#view .map-row:has-text('L4-201') .map-open")
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
        # 从 PCF 生成架构草稿：只验证勾选与预览，不落库
        def pcf_draft_wizard() -> None:
            goto("map")
            page.click('#view button:has-text("从 PCF 生成")')
            page.wait_for_selector("#mask.show")
            page.wait_for_selector("#pcfTree .pcf-node", timeout=8000)
            options = page.eval_on_selector_all(
                "#pcfFramework option", "els => els.map(e => e.value)"
            )
            assert {"APQC_PCF", "APQC_PCF_CP", "APQC_PCF_CE"} <= set(options), options

            page.fill("#pcfSearch", "建立和维护流程管理治理")
            page.wait_for_timeout(400)
            leaf = page.locator(
                '#pcfTree label.pcf-label:has-text("建立和维护流程管理治理") input'
            ).first
            leaf.check()
            page.click('#mFoot button:has-text("预览")')
            page.wait_for_selector('#pcfPreview:has-text("将新建")', timeout=8000)
            text = page.inner_text("#pcfPreview")
            assert "L3 新建 1" in text, text
            assert "L4 新建 4" in text, text
            assert "L1 新建 1" in text and "L2 新建 1" in text, text
            close_modal()

        # 从启动页直接进入 1+3+10 引导：选 1 个 L1 → 3 个 L2 → 10 个 L3
        def pcf_guided_wizard() -> None:
            goto("start")
            page.wait_for_timeout(700)
            page.click('#view .start-nav-item:has-text("流程架构设计")')
            page.wait_for_timeout(300)
            page.click('#view button:has-text("1+3+10 建架构")')
            page.wait_for_selector("#mask.show", timeout=8000)
            page.wait_for_selector('#pcfGuided input[data-act="map.guidedL1"]', timeout=12000)
            assert page.inner_text("#pageTitle") == "企业流程地图"
            page.locator('#pcfGuided input[data-act="map.guidedL1"]').first.check()
            page.wait_for_timeout(400)
            page.click('#pcfGuided button:has-text("套用推荐")')
            page.wait_for_timeout(500)
            guided = page.inner_text("#pcfGuided")
            assert "已选 3/3" in guided, guided[:240]
            assert "已选 0/10" not in guided, guided[:240]
            page.click('#mFoot button:has-text("预览")')
            page.wait_for_selector('#pcfPreview:has-text("将新建")', timeout=8000)
            close_modal()

        # PCF 分类浏览：层级、双语、官方定义与指标
        def pcf_browser() -> None:
            goto("pcf")
            page.wait_for_selector("#pcfRows .pcf-row", timeout=12000)
            text = page.inner_text("#view")
            assert "L1 流程类" in text and "L5 任务" in text, text[:200]
            assert "PCF 是分类，不是流程图" in text
            assert page.locator("#pcfRows .pcf-row").count() >= 13

            page.fill("#pcfQ", "采购物料与服务")
            page.wait_for_timeout(500)
            assert "采购物料与服务" in page.inner_text("#pcfRows")
            page.click('#pcfRows .pcf-row-main:has-text("采购物料与服务")')
            page.wait_for_selector("#pcfDetail h3", timeout=8000)
            detail = page.inner_text("#pcfDetail")
            assert "Procure materials and services" in detail, detail[:160]
            assert "PCF ID 10216" in detail, detail[:160]
            assert "官方定义" in detail
            # 中文名优先展示，且必须标出中文来源（官方中文整理版 / 参考译文 / 未译）
            assert "采购物料与服务" in detail, detail[:160]
            assert "官方中文版" in detail, detail[:160]

            page.wait_for_selector("#pcfMetricBox table", timeout=10000)
            assert "指标 ID" in page.inner_text("#pcfMetricBox")
            # 指标表下方必须标注「参考译文」，不能让自建译名被当成官方口径
            assert "参考译文" in page.inner_text("#pcfMetricBox")

        # 交互原语：confirm / prompt 走自建模态框，关闭等于取消
        def ui_dialogs() -> None:
            goto("dashboard")
            ok = page.evaluate(
                """async () => {
                  const ui = await import('/static/js/core/ui.js');
                  const pending = ui.confirmDialog('确认测试');
                  document.getElementById('uiDialogOk').click();
                  return await pending;
                }"""
            )
            assert ok is True, ok

            cancelled = page.evaluate(
                """async () => {
                  const ui = await import('/static/js/core/ui.js');
                  const pending = ui.confirmDialog('取消测试');
                  document.getElementById('uiDialogCancel').click();
                  return await pending;
                }"""
            )
            assert cancelled is False, cancelled

            closed = page.evaluate(
                """async () => {
                  const ui = await import('/static/js/core/ui.js');
                  const pending = ui.confirmDialog('关闭测试');
                  ui.closeModal();
                  return await pending;
                }"""
            )
            assert closed is False, closed

            answer = page.evaluate(
                """async () => {
                  const ui = await import('/static/js/core/ui.js');
                  const pending = ui.promptDialog('输入测试', {value: 'abc'});
                  document.getElementById('uiDialogInput').value = 'xyz';
                  document.getElementById('uiDialogOk').click();
                  return await pending;
                }"""
            )
            assert answer == "xyz", answer

        def benchmark_switch() -> None:
            goto("map")
            options = page.eval_on_selector_all(
                "#view select[title='切换对标框架'] option", "els => els.map(e => e.value)"
            )
            assert {"SCOR", "APQC_PCF", "APQC_PCF_CP", "APQC_PCF_CE"} <= set(options), options

            page.select_option("#view select[title='切换对标框架']", "SCOR")
            page.wait_for_selector("#view .card h3:has-text('SCOR')", timeout=8000)
            page.wait_for_selector("#view .map-bench-pill", state="visible", timeout=8000)
            text = page.inner_text("#view")
            assert "24/28" in text, f"SCOR 覆盖率渲染异常：{text[:160]!r}"
            assert "L3-010" in text, "SCOR 应显示研发类未覆盖流程"

            page.select_option("#view select[title='切换对标框架']", "APQC_PCF")
            page.wait_for_selector("#view .card h3:has-text('跨行业')", timeout=8000)
            page.wait_for_selector("#view :text('28/28')", timeout=8000)
            text = page.inner_text("#view")
            assert "所有 L3 流程" in text, f"APQC 应全量覆盖：{text[:160]!r}"
            assert "主框架" in text, "APQC 跨行业版应标记为主框架"
            assert "分类框架来源与署名" in text, "应展示 APQC 署名"

            # 消费电子行业配置也能覆盖公司流程
            page.select_option("#view select[title='切换对标框架']", "APQC_PCF_CE")
            page.wait_for_selector("#view .card h3:has-text('消费电子')", timeout=8000)
            page.wait_for_selector("#view :text('28/28')", timeout=8000)
            assert "消费电子" in page.inner_text("#view")

            page.select_option("#view select[title='切换对标框架']", "APQC_PCF")
            page.wait_for_selector("#view .card h3:has-text('跨行业')", timeout=8000)
            page.wait_for_selector("#view .map-bench-pill", state="visible", timeout=8000)
            page.click("#view .map-bench-pill >> nth=0")
            page.wait_for_selector("#mBody table", state="visible")
            assert "编码" in page.inner_text("#mBody")
            assert "查看 PCF 指标" in page.inner_text("#mFoot"), "分类弹窗应提供指标入口"

            page.click('#mFoot button:has-text("查看 PCF 指标")')
            page.wait_for_selector("#mBody table", state="visible")
            body = page.inner_text("#mBody")
            assert "指标 ID" in body and "公式" in body, body[:160]
            close_modal()

        # 项目工作台：阶段骨架、步骤闭环与退出门槛
        def workflow_workbench() -> None:
            goto("workflow")
            view = page.inner_text("#view")
            assert "项目工作台" in view, "工作台不是默认页签"
            nodes = page.eval_on_selector_all("#view .wb-stage-node", "els => els.length")
            assert nodes == 5, f"阶段骨架应为 5 个节点：{nodes}"
            assert page.locator("#view .wb-stage-side .wb-stage-node").count() == 5, (
                "阶段导航没有落在左侧栏"
            )
            assert "阶段退出门槛" in view, "工作台缺少退出门槛"
            assert page.locator("#view .wb-timeline .wb-tl-item").count() >= 1, (
                "当前阶段没有竖向时间线"
            )
            assert page.locator("#view .wb-tl-card[open]").count() == 0, "步骤卡默认不应展开"
            # 点击标题才展开；再点收起
            timeline_card = page.locator("#view .wb-tl-card").first
            timeline_head = timeline_card.locator(".wb-tl-head")
            timeline_head.click()
            page.wait_for_timeout(200)
            assert page.locator("#view .wb-tl-card[open]").count() == 1, "步骤卡不能展开"
            timeline_head.click()
            page.wait_for_timeout(200)
            assert page.locator("#view .wb-tl-card[open]").count() == 0, "步骤卡不能折叠"
            timeline_head.click()
            page.wait_for_timeout(200)

            advance = page.locator("#view .wb-advance")
            assert advance.count() == 1, "工作台缺少推进按钮"
            if advance.first.is_disabled():
                assert "当前不能推进" in view or "仍有未关闭条件" in view, (
                    "推进被阻断时没有给出原因"
                )

            page.click('#view .wb-tl-card[open] button[data-act="workflow.editStep"] >> nth=0')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            for marker in ("状态", "验收证据", "处理要点", "下一步"):
                assert marker in body, f"步骤闭环弹窗缺少「{marker}」"
            close_modal()

        # 标准工作流：步骤详情
        def workflow_step_modal() -> None:
            goto_workflow_tab("五阶段步骤")
            assert "推荐知识" in page.inner_text("#view"), "步骤清单没有显示推荐知识数"
            page.click("#view .step >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_selector("#wfRec h3", timeout=8000)
            body = page.inner_text("#mBody")
            assert "标准动作" in body and "关键要点" in body, body[:120]
            assert "推荐工具与预制模板" in body, "步骤弹窗缺少推荐工具区域"
            assert "该步骤还没有配置工具" in body, "1.1 没有配置工具，应给出提示"
            assert "本步骤推荐知识" in body, "步骤弹窗缺少推荐知识区域"
            assert "RACI" in body or "BPR" in body, "阶段 1 没有推送知识"
            close_modal()
            page.wait_for_timeout(300)

        # 步骤页推荐工具与模板：阶段 2 的 2.1 应有 SIPOC（必用）
        def workflow_step_recommendations() -> None:
            goto_workflow_tab("五阶段步骤")
            page.click('#view .stage-pill:has-text("阶段2")')
            page.wait_for_timeout(500)
            page.click('#view .wf-step:has-text("现状流程绘制")')
            page.wait_for_selector("#wfRec table", timeout=8000)
            body = page.inner_text("#wfRec")
            assert "SIPOC" in body and "必用" in body, f"推荐工具未渲染：{body[:200]!r}"
            assert "SWIMLANE" in body and "推荐" in body
            assert "验证" in body, "步骤推荐工具缺少验证标准"
            assert "暂无预制模板" in body, "未上传模板时应显示空态"
            close_modal()

        # 步骤页 → 工具箱：只展示本步骤推荐工具，并标注使用要求
        def step_to_filtered_toolbox() -> None:
            goto_workflow_tab("五阶段步骤")
            page.click('#view .stage-pill:has-text("阶段2")')
            page.wait_for_timeout(500)
            page.click('#view .wf-step:has-text("现状流程绘制")')
            page.wait_for_selector("#wfRec table", timeout=8000)
            page.click('#mFoot button:has-text("去工具箱看推荐工具")')
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "方法论工具箱"
            text = page.inner_text("#view")
            assert "只显示" in text and "现状流程绘制" in text, text[:200]
            assert "必用" in text and "推荐" in text, "工具使用要求标签未渲染"
            names = page.eval_on_selector_all(
                "#view .tb-card .tb-card-title b", "els => els.map(e => e.textContent.trim())"
            )
            assert len(names) == 2, f"过滤后应只有 2 个工具：{names}"
            assert any("SIPOC" in n for n in names) and any(
                "Swimlane" in n or "泳道" in n for n in names
            )

            # 工具详情应显示场景/验证标准，并在有步骤上下文时提供「用到步骤」
            page.click('#view .tb-card button:has-text("查看详情") >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(600)
            body = page.inner_text("#mBody")
            assert "适用场景" in body, "工具详情缺少适用场景"
            assert "验证标准" in body and "不适用" in body, "工具详情缺少决策字段"
            assert "用到步骤 2.1" in page.inner_text("#mFoot"), "工具详情缺少用到当前步骤入口"
            close_modal()
            page.wait_for_timeout(400)

            page.click('#view button:has-text("显示全部工具")')
            page.wait_for_timeout(900)
            names_all = page.eval_on_selector_all(
                "#view .tb-nav-item .tb-nav-name", "els => els.map(e => e.textContent.trim())"
            )
            assert len(names_all) > 2, f"清除过滤后左侧工具导航应显示更多工具：{names_all}"

        # 方法论匹配引擎（真实调用后端）
        def workflow_recommend() -> None:
            goto_workflow_tab("方法论匹配")
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
            page.click("#view .project-open >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            assert "概览" in page.inner_text("#mBody"), "详情弹窗未渲染"
            assert "改善项目卡" in page.inner_text("#mBody"), "项目概览缺少改善项目卡"
            assert "门禁签收" in page.inner_text("#mFoot"), "项目详情缺少门禁签收入口"
            assert "复制资产包" in page.inner_text("#mFoot"), "项目详情缺少复制资产包入口"
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

        # 工作流推进：从步骤直达工作现场、记录进度、按步骤看交付物
        def project_step_actions() -> None:
            goto("projects")
            page.click("#view .project-open >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            page.click('#mBody .tabs button:has-text("工作流推进")')
            page.wait_for_selector("#pd-wk", timeout=8000)
            page.wait_for_timeout(300)
            assert page.locator('#pd-wk button[data-act="projects.openStepWork"]').count(), (
                "步骤缺少「去工作」入口"
            )
            assert page.locator('#pd-wk button[data-act="projects.openStepTool"]').count(), (
                "步骤缺少「工具」入口"
            )
            assert page.locator('#pd-wk button[data-act="projects.logStep"]').count(), (
                "步骤缺少「记录进度」入口"
            )
            btn = page.locator('#pd-wk button[data-act="projects.openStepDeliverables"]').first
            assert btn.count(), "步骤没有交付物入口"
            step_no = btn.get_attribute("data-step")
            btn.click()
            page.wait_for_selector('#view button[data-act="dlv.clearStep"]', timeout=8000)
            assert page.inner_text("#pageTitle") == "交付物与模板库"
            assert f"step={step_no}" in page.url, f"URL 没有记录步骤筛选：{page.url}"
            assert "只显示步骤" in page.inner_text("#view"), "交付物页没有进入步骤筛选"
            rows = page.locator("#dlvList tbody tr").count()
            assert rows > 0, "步骤筛选后没有交付物"
            page.click('#view button[data-act="dlv.clearStep"]')
            page.wait_for_function(
                """(before) => document.querySelectorAll('#dlvList tbody tr').length > before""",
                arg=rows,
                timeout=8000,
            )

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

        # 立项向导里打开工具详情，关闭工具后必须回到原向导，不能丢失已填内容
        def wizard_tool_modal() -> None:
            goto("projects")
            page.click("text=+ 新建流程项目")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            page.fill("#npName", "向导保留测试")
            page.click("#npRecBtn")
            page.wait_for_selector('#npResult button[data-act="toolbox.open"]', timeout=8000)
            page.click('#npResult button[data-act="toolbox.open"] >> nth=0')
            page.wait_for_selector('#mFoot button[data-act="toolbox.close"]', timeout=8000)
            page.wait_for_timeout(300)
            page.click('#mFoot button[data-act="toolbox.close"]')
            page.wait_for_timeout(400)
            assert page.is_visible("#mask.show"), "关闭工具详情后立项向导被一起关闭"
            assert "立项向导" in page.inner_text("#mTitle"), "关闭工具详情后没有回到立项向导"
            assert page.input_value("#npName") == "向导保留测试", "回到向导后已填内容丢失"
            page.click('#mFoot button[data-act="projects.close"]')
            page.wait_for_timeout(300)
            assert not page.is_visible("#mask.show"), "取消后向导没有关闭"

        # 工具箱：详情 + 按问题找工具（预设问题 + 自由输入各测一次）
        def toolbox() -> None:
            goto("toolbox")
            page.wait_for_timeout(900)
            view = page.inner_text("#view")
            assert "我遇到了什么问题" in view, "工具箱首屏没有问题入口"
            assert "按问题" in view and "全部资源" in view, "工具箱缺少问题导航或全部资源区"
            assert "新建工具" in view and "新建案例/模板" in view, "管理员工具箱缺少新建入口"

            # 左栏四个折叠区共用一套互斥手风琴：点开一个，其他必须收起
            for label in ("按阶段", "按资源类型", "工具目录", "按问题"):
                page.click(f'#view .kb-nav-fold summary:has-text("{label}")')
                page.wait_for_timeout(1200)
                opened = page.eval_on_selector_all(
                    "#view .kb-nav-fold",
                    "els => els.filter((el) => el.open).length",
                )
                assert opened == 1, f"左栏「{label}」展开后同时有 {opened} 个折叠区打开"

            page.click('#view button[data-act="toolbox.newTool"]')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(500)
            modal = page.inner_text("#mBody")
            assert "工具编码" in modal and "适用场景" in modal, "新建工具表单缺少字段"
            close_modal()
            page.wait_for_timeout(400)

            page.click('#view .kb-pain[data-scenario="RACI"]')
            page.wait_for_timeout(1600)
            res = page.inner_text("#view")
            assert "匹配结果" in res and "验证标准" in res, f"快捷痛点未出结果：{res[:200]!r}"
            assert "适配" in res, "匹配结果缺少适配度"
            assert "配套案例 / 模板" in res, "问题匹配后没有带出配套案例/模板"

            page.click('#view .tb-card button[data-act="toolbox.open"] >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            body = page.inner_text("#mBody")
            assert "标准操作步骤" in body, f"工具详情缺少步骤：{body[:160]!r}"
            assert "常见误用" in body, "工具详情缺少常见误用"
            assert "验证标准" in body and "不适用" in body, "工具详情缺少决策字段"
            assert "相关案例" in body, "工具详情缺少关联知识区"
            assert "已发布" in body or "已验证" in body, "工具详情缺少维护状态"
            assert "加入使用计划" in page.inner_text("#mFoot"), "工具详情缺少使用计划入口"
            page.click('#mFoot button:has-text("加入使用计划")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            plan_body = page.inner_text("#mask")
            assert "关联步骤" in plan_body and "验证标准" in plan_body, "使用计划弹窗缺字段"
            close_modal()
            page.wait_for_timeout(600)

            page.fill("#toolQ", "跨部门互相推诿")
            page.click('#view button[data-act="toolbox.match"]')
            page.wait_for_timeout(1600)
            res2 = page.inner_text("#view")
            assert "RACI" in res2, f"自由输入应匹配到 RACI：{res2[:240]!r}"

            # 工具类别属于「工具目录」，不属于「按资源类型」
            page.click('#view .kb-nav-fold summary:has-text("按资源类型")')
            page.wait_for_timeout(500)
            assert not page.locator(
                '#view button[data-act="toolbox.toggleCategory"]'
            ).first.is_visible(), "工具类别不应出现在「按资源类型」折叠区"
            page.click('#view .kb-nav-fold summary:has-text("工具目录")')
            page.wait_for_timeout(500)
            assert page.locator(
                '#view button[data-act="toolbox.toggleCategory"]'
            ).first.is_visible(), "「工具目录」折叠区缺少工具类别筛选"
            # 四象限是辅助筛选，不是主入口
            page.click('#view button[data-act="toolbox.toggleCategory"][data-category="DIAGNOSE"]')
            page.wait_for_timeout(1200)
            assert "方法论工具箱" in page.inner_text("#view")
            assert "category=" in page.url, f"URL 没有记录四象限筛选：{page.url}"

            # 工具详情 → 按问题/按阶段：必须退出工具详情，不能停留在工具界面
            # 上一步点工具类别后「工具目录」已经是展开状态，直接点工具项
            nav_item = page.locator("#view .tb-nav-item").first
            assert nav_item.count(), "工具目录没有工具项"
            nav_item.click()
            page.wait_for_timeout(1200)
            assert page.locator("#view .tb-detail-card").count(), "点击工具项后没有进入工具详情"
            page.click('#view .kb-nav-fold summary:has-text("按问题")')
            page.wait_for_timeout(1200)
            assert page.locator("#view .tb-detail-card").count() == 0, (
                "切到「按问题」后仍停留在工具详情"
            )
            assert "我遇到了什么问题" in page.inner_text("#view"), (
                "切到「按问题」后没有回到问题区块"
            )
            page.click('#view .kb-nav-fold summary:has-text("按阶段")')
            page.wait_for_timeout(1200)
            assert page.locator("#view .tb-detail-card").count() == 0, (
                "切到「按阶段」后仍停留在工具详情"
            )

        # 项目交付物：把已发布流程模型登记为 2.1 的证据，不复制文件
        def deliverable_model_link() -> None:
            setup = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const h = {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'};
                  const suffix = Math.random().toString(36).slice(2, 7).toUpperCase();
                  const proc = await fetch('/api/v1/process-map', {
                    method: 'POST', headers: h,
                    body: JSON.stringify({code: 'L3-MDL-' + suffix, name: 'E2E 模型来源流程', level: 3}),
                  }).then((r) => r.json());
                  await fetch('/api/v1/processes/' + proc.id + '/design', {
                    method: 'PUT', headers: h,
                    body: JSON.stringify({nodes: [{node_key: 'a', name: 'E2E活动',
                      node_type: 'TASK', lane: 'L', duration_minutes: 10}], edges: []}),
                  });
                  const pub = await fetch('/api/v1/processes/' + proc.id + '/design/publish', {
                    method: 'POST', headers: h, body: JSON.stringify({}),
                  }).then((r) => r.json());
                  const proj = await fetch('/api/v1/projects', {
                    method: 'POST', headers: h,
                    body: JSON.stringify({name: 'E2E 模型来源项目 ' + suffix,
                      methodology: 'BPI', owner: '流程管理科', process_id: proc.id}),
                  }).then((r) => r.json());
                  return {processId: proc.id, projectId: proj.id, versionId: pub.version_id};
                }"""
            )
            try:
                goto("deliverables")
                page.click('#view .tabs button:has-text("项目交付物")')
                page.wait_for_timeout(600)
                page.select_option(
                    '#view select[data-act="dlv.project"]', value=str(setup["projectId"])
                )
                page.wait_for_selector("#dlvList table", timeout=8000)
                page.wait_for_timeout(600)
                row = page.locator('#dlvList tr:has-text("2.1")').first
                row.locator('button[data-act="dlv.linkModel"]').click()
                page.wait_for_selector("#lmVersion", timeout=8000)
                page.select_option("#lmVersion", value=str(setup["versionId"]))
                page.click('#mFoot button[data-act="dlv.submitLinkModel"]')
                page.wait_for_function(
                    """() => {
                      const row = [...document.querySelectorAll('#dlvList tr')]
                        .find((r) => r.textContent.includes('2.1'));
                      return !!row && row.textContent.includes('已生效');
                    }""",
                    timeout=8000,
                )
                text = page.locator('#dlvList tr:has-text("2.1")').first.inner_text()
                assert "已生效" in text, f"已发布模型应直接计为已生效：{text[:200]}"
            finally:
                page.evaluate(
                    """async ({projectId, processId}) => {
                      const t = localStorage.getItem('psm_token');
                      const h = {Authorization: 'Bearer ' + t};
                      await fetch('/api/v1/projects/' + projectId, {method: 'DELETE', headers: h});
                      await fetch('/api/v1/process-map/' + processId, {method: 'DELETE', headers: h});
                    }""",
                    setup,
                )

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
            assert "关联活动" in body, "新建标准文件弹窗缺少活动绑定"
            assert "适用范围" in body and "集团总部" in body, "新建标准文件缺少组织范围"
            assert "变体策略" in body and "依据上级标准" in body, "新建标准文件缺少变体配置"
            close_modal()

            # 选择组织后应出现有效版本解析（当前无标准文件 → 空态）
            page.locator('#view select[data-act="dlv.docOrg"]').select_option(
                label="华东分公司（公司/分公司）"
            )
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

        # 项目交付物：新建版本（选工具/模板或空白登记）
        def deliverable_new_version() -> None:
            project_id = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const r = await fetch('/api/v1/projects', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json',
                               Authorization: 'Bearer ' + t },
                    body: JSON.stringify({ name: '自检用新建交付物项目', methodology: 'BPI',
                      owner: '自检员', start_date: '2026-10-01', end_date: '2027-03-31' })
                  });
                  return (await r.json()).id;
                }"""
            )
            try:
                goto("deliverables")
                page.click('#view .tabs button:has-text("项目交付物")')
                page.wait_for_timeout(800)
                page.select_option("#view select.sel", str(project_id))
                page.wait_for_timeout(1200)
                row_btn = page.locator(
                    '#dlvList tr:has-text("2.1") button[data-act="dlv.newVersion"]'
                )
                assert row_btn.count(), "2.1 行没有新建入口"
                row_btn.first.click()
                page.wait_for_selector("#nvTitle", timeout=8000)
                body = page.inner_text("#mBody")
                assert "SIPOC" in body, "新建交付物弹窗没有展示本步骤推荐工具"
                assert "空白新建" in body, "新建交付物弹窗缺少空白新建"
                assert "去工具箱选工具" in page.inner_text("#mFoot"), "缺少工具选择入口"
                page.fill("#nvTitle", "自检新建版本")
                page.click('#mBody button[data-act="dlv.createBlank"]')
                page.wait_for_timeout(1500)
                assert "已新建" in page.inner_text("#toast"), page.inner_text("#toast")
                page.wait_for_function(
                    """() => document.getElementById('dlvList')?.innerText.includes('R1')""",
                    timeout=8000,
                )
            finally:
                page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/projects/' + pid,
                        { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } });
                    }""",
                    int(project_id),
                )

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
            tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            tmp.write(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF")
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

                # PDF 应能内联预览；Office/Visio 仍提示下载
                page.click('#dlvList button[data-act="dlv.preview"] >> nth=0')
                page.wait_for_selector("#mask.show")
                page.wait_for_selector(".preview-frame", timeout=8000)
                assert "预览" in page.inner_text("#mTitle")
                close_modal()
                page.wait_for_timeout(300)

                # 打印清单：新窗口应包含项目与交付物表头
                with page.expect_popup() as popup_info:
                    page.click('#view button[data-act="dlv.printList"]')
                popup = popup_info.value
                popup.wait_for_timeout(600)
                assert "项目交付物清单" in popup.content()
                popup.close()

                # 打印包：服务端 HTML，含阶段门槛与交付物
                with page.expect_popup() as pack_info:
                    page.click('#view button[data-act="dlv.printPack"]')
                pack = pack_info.value
                pack.wait_for_function(
                    """() => document.body.innerText.includes('项目交付物打印包')""",
                    timeout=8000,
                )
                assert "阶段退出门槛" in pack.content()
                pack.close()
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

            # 岗位主数据：新建 → 列表出现 → 删除
            suffix = str(int(time.time() * 1000))[-5:]
            position_code = "POS-E2E" + suffix
            position_name = "E2E岗位" + suffix
            page.click('#view .tabs button:has-text("岗位")')
            page.wait_for_timeout(500)
            assert "岗位主数据" in page.inner_text("#view")
            page.click('#view button:has-text("+ 新建岗位")')
            page.wait_for_selector("#mask.show")
            assert "岗位编码" in page.inner_text("#mBody")
            page.fill("#posCode", position_code)
            page.fill("#posName", position_name)
            page.click('#mFoot button:has-text("创建")')
            page.wait_for_timeout(1000)
            assert position_name in page.inner_text("#view")
            row = page.locator("#view tr").filter(has_text=position_name).first
            row.locator('button:has-text("删除")').click()
            page.wait_for_selector("#uiDialogOk", timeout=5000)
            assert "删除岗位" in page.inner_text("#mBody")
            page.click("#uiDialogOk")
            page.wait_for_timeout(1000)
            assert position_name not in page.inner_text("#view")

            # 治理角色：与系统权限分离的角色主数据
            page.click('#view .tabs button:has-text("治理角色")')
            page.wait_for_timeout(600)
            gov = page.inner_text("#view")
            assert "治理角色" in gov and "新建治理角色" in gov, gov[:200]
            page.click('#view button:has-text("+ 新建治理角色")')
            page.wait_for_selector("#mask.show")
            modal = page.inner_text("#mBody")
            assert "角色名称" in modal and "角色类型" in modal, modal[:160]
            close_modal()
            page.wait_for_timeout(300)

        # 草图：draw.io embed 的 proto=json 收发的是 JSON 字符串
        def sketch_drawio_protocol() -> None:
            created = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const r = await fetch('/api/v1/sketches', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + t},
                    body: JSON.stringify({title: 'E2E 草图协议'}),
                  });
                  return await r.json();
                }"""
            )
            sketch_id = created["id"]
            try:
                goto("sketches")
                row = page.locator("#view tr").filter(has_text="E2E 草图协议")
                row.locator('button:has-text("打开")').click()
                page.wait_for_selector("#drawioFrame", timeout=8000)
                page.wait_for_timeout(600)
                origin = page.evaluate(
                    """async () => {
                      const t = localStorage.getItem('psm_token');
                      const meta = await fetch('/api/v1/sketches/meta', {
                        headers: {'Authorization': 'Bearer ' + t},
                      }).then(r => r.json());
                      const origin = new URL(meta.embed_url, location.origin).origin;
                      const frame = document.getElementById('drawioFrame');
                      const send = (payload) => window.dispatchEvent(new MessageEvent('message', {
                        data: JSON.stringify(payload), origin, source: frame.contentWindow,
                      }));
                      send({event: 'init'});
                      send({
                        event: 'save',
                        xml: '<mxfile host="e2e"><diagram id="d1">E2E-OK</diagram></mxfile>',
                      });
                      return origin;
                    }"""
                )
                assert origin, "没有取到 draw.io embed 来源"
                page.wait_for_timeout(1200)
                assert "草图已保存" in page.inner_text("#toast")
                detail = page.evaluate(
                    """async (id) => {
                      const t = localStorage.getItem('psm_token');
                      return await fetch('/api/v1/sketches/' + id, {
                        headers: {'Authorization': 'Bearer ' + t},
                      }).then(r => r.json());
                    }""",
                    sketch_id,
                )
                assert "E2E-OK" in (detail.get("mxfile_xml") or ""), detail.get("mxfile_xml")
                page.click('#mFoot button:has-text("关闭")')
                page.wait_for_timeout(300)

                # 删除确认走自建模态框（不是浏览器原生 confirm）
                row.locator('button:has-text("删除")').click()
                page.wait_for_selector("#uiDialogOk", timeout=5000)
                assert "确定删除这张架构草图" in page.inner_text("#mBody")
                page.click("#uiDialogCancel")
                page.wait_for_timeout(300)
                assert not page.locator("#mask").evaluate("e => e.classList.contains('show')")
            finally:
                page.evaluate(
                    """async (id) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/sketches/' + id, {
                        method: 'DELETE', headers: {'Authorization': 'Bearer ' + t},
                      });
                    }""",
                    sketch_id,
                )

        # 架构树计数：L1「研发设计」下含 9 个 L4 活动
        def map_tree_counts() -> None:
            goto("map")
            page.click('.crumb a:has-text("全部价值链")')
            page.wait_for_timeout(600)
            item = page.locator("#view .tree-item").filter(has_text="研发设计").first
            count = item.locator(".cnt")
            assert item.locator(".tree-level").inner_text().strip() == "L1"
            assert count.inner_text().strip() == "9", (
                f"L1 研发设计 L4 活动数错误：{count.inner_text()}"
            )
            assert "含 9 个 L4 活动" in (count.get_attribute("data-tip") or "")
            assert count.get_attribute("title") is None, "计数不应再使用浏览器原生 title 提示"

            # 左侧架构导航可折叠/展开
            page.click(".map-side-toggle")
            page.wait_for_timeout(300)
            assert page.locator(".map-layout").evaluate(
                "e => e.classList.contains('nav-collapsed')"
            ), "架构导航没有折叠"
            assert not page.locator(".map-tree").is_visible()
            page.click(".map-side-toggle")
            page.wait_for_timeout(300)
            assert page.locator(".map-tree").is_visible(), "架构导航没有展开"

        # 设计器：打开节点编辑，改等待时间，指标应变化
        # 评审中的流程为只读：调色板必须保留可见、可折叠，但创建工具不可用
        def designer_xml_pure_functions() -> None:
            """xml.js 是纯函数：在真实浏览器里 import 并跑特征样例。

            项目没有 Node 测试环境，这里用浏览器原生的 DOMParser/XMLSerializer
            验证泳道恢复、连线引用补齐、类型写入与折点正交化，
            避免只靠静态守卫（源码里有函数名 ≠ 函数能跑）。
            """
            errors = page.evaluate(
                """async () => {
                  const m = await import('/static/js/views/designer/xml.js');
                  const errors = [];
                  const expect = (ok, msg) => { if (!ok) errors.push(msg); };

                  // 1) 折点正交化：斜线补直角点
                  const pts = m.orthogonalizePath([
                    {x: 0, y: 0}, {x: 100, y: 50}, {x: 100, y: 200},
                  ]);
                  expect(pts.length === 3 && pts[1].x === 100 && pts[1].y === 0,
                    'orthogonalizePath 未补出正交折点: ' + JSON.stringify(pts));

                  const defs = (body) => `<?xml version="1.0" encoding="UTF-8"?>
                    <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                      xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                      xmlns:dc="http://www.omg.org/spec/DD/20100524/DC"
                      xmlns:pms="http://logix-pms.local/bpmn">
                      <bpmn:process id="P">${body}</bpmn:process>
                    </bpmn:definitions>`;

                  // 2) ensureFlowRefs：从 sequenceFlow 反推 incoming/outgoing
                  const refs = m.ensureFlowRefs(defs(
                    '<bpmn:startEvent id="A"/><bpmn:task id="B"/>' +
                    '<bpmn:sequenceFlow id="F" sourceRef="A" targetRef="B"/>'));
                  expect(/outgoing[^>]*>F</.test(refs), '缺少 outgoing 引用');
                  expect(/incoming[^>]*>F</.test(refs), '缺少 incoming 引用');

                  // 3) setPmsNodeType：写入 pms:nodeType 扩展
                  const typed = m.setPmsNodeType(defs('<bpmn:task id="B"/>'), 'B', 'APPROVAL');
                  expect(/nodeType[^>]*>APPROVAL</.test(typed),
                    'setPmsNodeType 没有写入扩展类型');

                  // 4) appendBpmnLane：新增泳道 + 默认活动，ID 不与现有节点冲突
                  const added = m.appendBpmnLane(defs('<bpmn:task id="n1"/>'), '财务', ['n1']);
                  expect(added && added.laneId === 'Lane_1' && added.taskId === 'n2',
                    'appendBpmnLane 返回的 ID 不符合预期: ' + JSON.stringify(added));
                  expect(added.xml.includes('name="财务"') && added.xml.includes('bpmn:lane'),
                    'appendBpmnLane 没有生成泳道');

                  // 5) restoreLanes：补回泳道 DI，并为标题栏留出横向偏移（200 + 80）
                  const withLane = `<?xml version="1.0" encoding="UTF-8"?>
                    <bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"
                      xmlns:bpmndi="http://www.omg.org/spec/BPMN/20100524/DI"
                      xmlns:dc="http://www.omg.org/spec/DD/20100524/DC">
                      <bpmn:process id="P">
                        <bpmn:laneSet id="LS"><bpmn:lane id="L1">
                          <bpmn:flowNodeRef>A</bpmn:flowNodeRef></bpmn:lane></bpmn:laneSet>
                        <bpmn:task id="A"/>
                      </bpmn:process>
                      <bpmndi:BPMNDiagram id="D"><bpmndi:BPMNPlane id="PL" bpmnElement="P">
                        <bpmndi:BPMNShape id="A_di" bpmnElement="A">
                          <dc:Bounds x="200" y="120" width="100" height="80"/></bpmndi:BPMNShape>
                      </bpmndi:BPMNPlane></bpmndi:BPMNDiagram>
                    </bpmn:definitions>`;
                  const restored = m.restoreLanes(withLane);
                  expect(restored.includes('bpmnElement="L1"'),
                    'restoreLanes 没有补回泳道 DI');
                  expect(/x="280"/.test(restored),
                    'restoreLanes 没有为泳道标题栏留出横向偏移');
                  return errors;
                }"""
            )
            assert not errors, "designer/xml.js 特征测试失败：\n" + "\n".join(errors)

        def designer_readonly_palette() -> None:
            goto("designer")
            picked = pick_review_design()
            if not picked:
                print("NOTICE 当前没有评审中的流程，跳过只读调色板检查")
                return
            page.wait_for_selector("#bpmnCanvas .djs-palette", state="visible", timeout=8000)
            assert page.locator("#bpmnCanvas").evaluate("e => e.classList.contains('readonly')"), (
                "评审中的流程应为只读"
            )
            assert page.locator(".djs-palette").is_visible(), "只读时调色板不应隐藏"
            opacity = page.eval_on_selector(
                '.djs-palette [data-action="create.task"]',
                "e => getComputedStyle(e).opacity",
            )
            assert float(opacity) < 1, "只读时创建工具应置灰"
            before = page.locator("#bpmnCanvas .djs-element").count()
            page.click('.djs-palette [data-action="create.task"]')
            page.wait_for_timeout(300)
            assert page.locator("#bpmnCanvas .djs-element").count() == before, (
                "只读时不应能创建元素"
            )
            page.click(".djs-palette-toggle")
            page.wait_for_timeout(300)
            assert not page.locator(".djs-palette").evaluate("e => e.classList.contains('open')")
            assert page.locator(".djs-palette").is_visible(), "折叠后调色板开关仍应可见"
            page.click(".djs-palette-toggle")
            page.wait_for_timeout(300)
            assert page.locator(".djs-palette").evaluate("e => e.classList.contains('open')")

        def designer_edit_node() -> None:
            goto("designer")
            pick_editable_design()
            page.wait_for_selector("#bpmnCanvas .djs-palette", state="visible", timeout=8000)
            page.wait_for_selector("#bpmnCanvas .djs-element", timeout=8000)
            assert page.locator("#bpmnCanvas .djs-element").count() >= 5, "画布没有渲染节点"
            select_bpmn_node("n3")
            if not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"):
                page.click("#bpmnPropsToggle")
            page.wait_for_selector("#bpmnSidebar.open #bpWait", timeout=8000)
            original_wait = page.input_value("#bpWait")
            page.fill("#bpWait", "0")
            page.click('#bpmnSidebar button:has-text("保存指标")')
            page.wait_for_timeout(1500)
            assert "节点属性已保存" in page.inner_text("#toast"), page.inner_text("#toast")

            # 还原演示数据，避免自检反复改写种子模型
            page.fill("#bpWait", original_wait)
            page.click('#bpmnSidebar button:has-text("保存指标")')
            page.wait_for_timeout(1500)
            page.click('#view .seg button:has-text("指标与建议")')
            page.wait_for_timeout(800)
            assert "流程周期效率" in page.inner_text("#view")
            page.screenshot(path=str(out_dir / "interaction-designer.png"), full_page=True)

        # 专业 BPMN 画布（bpmn-js）：加载、调色板、水印、自动布局
        def designer_bpmn_spike() -> None:
            goto("designer")
            pick_editable_design()
            if page.locator('#view .seg button:has-text("流程模型")').count():
                page.click('#view .seg button:has-text("流程模型")')
                page.wait_for_timeout(300)
            page.wait_for_selector("#bpmnCanvas .djs-palette", timeout=8000)
            page.wait_for_selector("#bpmnCanvas .djs-element", timeout=8000)
            assert page.locator("#bpmnCanvas .djs-element").count() >= 5
            assert page.locator(".bjs-powered-by").count() == 1, "bpmn.io 水印必须保留"
            # 执行引擎不支持的构造不应出现在调色板里；等待事件单独提供
            assert (
                page.locator('#bpmnCanvas [data-action="create.subprocess-expanded"]').count() == 0
            ), "调色板仍提供子流程"
            assert (
                page.locator('#bpmnCanvas [data-action="create.intermediate-event"]').count() == 0
            ), "调色板仍提供抛出/边界中间事件"
            assert page.locator('#bpmnCanvas [data-action="create.pms-wait-event"]').count() == 1, (
                "缺少等待事件入口"
            )
            assert page.locator('#bpmnCanvas [data-action="create.pms-approval"]').count() == 1, (
                "缺少审批节点入口"
            )
            assert page.locator('#bpmnCanvas [data-action="create.pms-handoff"]').count() == 1, (
                "缺少移交节点入口"
            )
            # 选中活动节点后，属性区应能直接维护节点分派 / SLA
            select_bpmn_node("n3")
            page.wait_for_timeout(400)
            assert not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"), (
                "单击不应自动打开属性栏"
            )
            # 上下文工具属于画布层，必须被右侧栏盖住，不能浮在栏里
            layers = page.evaluate(
                """() => {
                  const pad = document.querySelector('#bpmnCanvas .djs-context-pad.open');
                  const side = document.getElementById('bpmnSidebar');
                  return {
                    pad: pad ? getComputedStyle(pad).zIndex : null,
                    side: getComputedStyle(side).zIndex,
                  };
                }"""
            )
            assert layers["pad"], "选中节点后没有出现上下文工具"
            assert int(layers["side"]) > int(layers["pad"]), layers
            assert (
                page.locator('#bpmnCanvas [data-action="append.intermediate-event"]').count() == 0
            ), "上下文菜单仍能追加中间事件"
            assert page.locator('#bpmnCanvas [data-action="replace"]').count() == 1
            page.click('#bpmnCanvas [data-action="replace"]')
            page.wait_for_selector(".djs-popup [data-id]", timeout=5000)
            replace_ids = page.eval_on_selector_all(
                ".djs-popup [data-id]", "els => els.map(e => e.dataset.id)"
            )
            blocked = (
                "parallel-gateway",
                "complex-gateway",
                "event-based-gateway",
                "subprocess",
                "boundary",
                "transaction",
            )
            assert not [key for key in replace_ids if any(x in key for x in blocked)], replace_ids
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            # 双击只做画布内改名，不再打开侧栏
            start_bpmn_direct_editing("n3")
            page.wait_for_timeout(300)
            assert page.locator(".djs-direct-editing-parent").count() >= 1, (
                "双击改名（bpmn-js 原生编辑）被取消了"
            )
            assert not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"), (
                "双击改名不应同时打开属性栏"
            )
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            # 属性栏由工具栏按钮显式打开；选中只更新内容
            page.click("#bpmnPropsToggle")
            page.wait_for_selector("#bpmnSidebar.open #bpmnPropsPanel #baRole", timeout=8000)
            assert page.input_value("#bpName").strip(), "属性栏缺少可编辑的名称"
            # 适应画布必须避开调色板和右侧属性栏
            page.click('#view button:has-text("适应画布")')
            page.wait_for_timeout(500)
            palette_box = page.locator(".djs-palette").bounding_box()
            leftmost = page.evaluate(
                """() => Math.min(...[...document.querySelectorAll(
                  '#bpmnCanvas .djs-shape[data-element-id]')]
                  .filter(e => !e.getAttribute('data-element-id').startsWith('Lane_'))
                  .map(e => e.getBoundingClientRect().x))"""
            )
            assert palette_box and leftmost > palette_box["x"] + palette_box["width"], (
                leftmost,
                palette_box,
            )
            side_box = page.locator("#bpmnSidebar").bounding_box()
            rightmost = page.evaluate(
                """() => Math.max(...[...document.querySelectorAll(
                  '#bpmnCanvas .djs-shape[data-element-id]')]
                  .filter(e => !e.getAttribute('data-element-id').startsWith('Lane_'))
                  .map(e => e.getBoundingClientRect().right))"""
            )
            assert side_box and rightmost < side_box["x"], (rightmost, side_box)
            # 名称保存（保持原值，避免改写演示数据）
            page.click('#bpmnSidebar button:has-text("保存名称")')
            page.wait_for_timeout(1200)
            assert "名称已更新" in page.inner_text("#toast")
            assert page.locator("#bpmnSidebar .bpmn-assign").count() == 1
            page.fill("#baDue", "24")
            page.click('#bpmnSidebar button:has-text("保存执行配置")')
            page.wait_for_timeout(1200)
            assert "节点执行配置已保存" in page.inner_text("#toast")
            # 还原为空，避免自检留下演示配置
            page.fill("#baDue", "")
            page.click('#bpmnSidebar button:has-text("保存执行配置")')
            page.wait_for_timeout(1200)
            # 属性栏可收起，并可从工具栏重新打开
            page.click('#bpmnSidebar button:has-text("收起")')
            page.wait_for_timeout(300)
            assert not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"), (
                "属性栏没有收起"
            )
            page.click("#bpmnPropsToggle")
            page.wait_for_selector("#bpmnSidebar.open #baRole", timeout=5000)
            page.click('#view button:has-text("运行校验")')
            page.click("#bpmnLintToggle")
            page.wait_for_selector("#bpmnSidebar.open", timeout=5000)
            page.wait_for_selector(".bpmn-lint-item", timeout=8000)
            assert page.locator(".bpmn-lint-item").count() >= 1
            lint_text = page.inner_text("#bpmnLint")
            assert any(
                phrase in lint_text
                for phrase in (
                    "缺少开始节点",
                    "缺少结束节点",
                    "节点被当作隐式",
                    "多路汇入没有网关",
                    "连线标签不会生效",
                )
            ), lint_text[:300]
            assert "Process is missing" not in lint_text, "校验结果仍在显示原始英文规则消息"
            # 适应画布按钮应在工具栏水平居中
            fit_box = page.locator(".bpmn-fit-btn").bounding_box()
            bar_box = page.locator(".bpmn-toolbar").bounding_box()
            assert fit_box and bar_box
            assert (
                abs((fit_box["x"] + fit_box["width"] / 2) - (bar_box["x"] + bar_box["width"] / 2))
                <= 4
            ), (fit_box, bar_box)
            page.click('#view button:has-text("全屏")')
            page.wait_for_timeout(400)
            assert page.locator("#bpmnCard").evaluate("e => e.classList.contains('fullscreen')")
            assert not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"), (
                "进入全屏后属性/校验侧栏应收起"
            )
            canvas_box = page.locator("#bpmnCanvas").bounding_box()
            assert canvas_box and canvas_box["height"] >= 550, canvas_box
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            assert not page.locator("#bpmnCard").evaluate("e => e.classList.contains('fullscreen')")
            # 自动布局必须保留泳道；bpmn-auto-layout 本身只排 flowElements
            page.click('#view button:has-text("自动布局")')
            page.wait_for_selector("#uiDialogOk", timeout=5000)
            page.click("#uiDialogOk")
            page.wait_for_timeout(5000)
            assert "已自动布局并保存" in page.inner_text("#toast")
            assert page.locator('#bpmnCanvas [data-element-id^="Lane_"]').count() >= 1, (
                "自动布局后泳道丢失"
            )
            # 跨泳道重排后连线必须保持正交，不能出现斜穿泳道的线段
            diagonals = page.evaluate(
                """async () => {
                  const t = localStorage.getItem('psm_token');
                  const pid = window.state.designer.processId;
                  const xml = await fetch('/api/v1/processes/' + pid + '/bpmn',
                    { headers: { Authorization: 'Bearer ' + t } }).then(r => r.text());
                  const doc = new DOMParser().parseFromString(xml, 'application/xml');
                  const ns = 'http://www.omg.org/spec/BPMN/20100524/DI';
                  const bad = [];
                  for (const edge of doc.getElementsByTagNameNS(ns, 'BPMNEdge')) {
                    const pts = [...edge.children]
                      .filter(c => c.localName === 'waypoint')
                      .map(c => ({ x: +c.getAttribute('x'), y: +c.getAttribute('y') }));
                    for (let i = 1; i < pts.length; i += 1) {
                      if (Math.abs(pts[i].x - pts[i - 1].x) > 0.5
                          && Math.abs(pts[i].y - pts[i - 1].y) > 0.5) {
                        bad.push({ flow: edge.getAttribute('bpmnElement'), from: pts[i - 1], to: pts[i] });
                      }
                    }
                  }
                  return bad;
                }"""
            )
            assert not diagonals, f"自动布局后仍有斜线连线：{diagonals[:3]}"
            page.screenshot(path=str(out_dir / "interaction-designer-bpmnjs.png"), full_page=True)

        # 设计器：草稿 → 评审 → 发布，版本历史可打开
        # bpmn-js 属性侧栏：节点负责人/类型/泳道、新增泳道、连线条件与概率
        def designer_bpmn_properties() -> None:
            goto("designer")
            pick_editable_design()
            page.wait_for_timeout(1000)
            page.wait_for_selector("#bpmnCanvas .djs-palette", state="visible", timeout=8000)
            pid = page.evaluate("() => window.state.designer.processId")

            def design_model() -> dict:
                return page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      return await fetch('/api/v1/processes/' + pid + '/design',
                        {headers: {Authorization: 'Bearer ' + t}}).then(r => r.json());
                    }""",
                    pid,
                )

            def ensure_sidebar() -> None:
                if not page.locator("#bpmnSidebar").evaluate("e => e.classList.contains('open')"):
                    page.click("#bpmnPropsToggle")
                page.wait_for_selector("#bpmnSidebar.open", timeout=5000)
                page.wait_for_timeout(200)

            model = design_model()
            row = next(item for item in model["nodes"] if item["node_type"] in ("TASK", "APPROVAL"))
            node_key = row["node_key"]
            # 自动布局下连线命中区可能压过节点，直接走 bpmn-js 选择 API，避免点选被连线截获。
            page.evaluate(
                """(key) => {
                  const modeler = window.__bpmnSpike.modeler;
                  const element = modeler.get('elementRegistry').get(key);
                  modeler.get('selection').select(element);
                }""",
                node_key,
            )
            page.wait_for_timeout(300)
            ensure_sidebar()
            page.wait_for_selector("#bpPosition", timeout=5000)

            # 负责人岗位（主数据）
            original_position = page.input_value("#bpPosition")
            position_options = page.eval_on_selector_all(
                "#bpPosition option", "els => els.map(e => e.value).filter(Boolean)"
            )
            target_position = next(
                (item for item in position_options if item != original_position), None
            )
            assert target_position, position_options
            page.select_option("#bpPosition", target_position)
            page.click('#bpmnSidebar button:has-text("保存指标")')
            page.wait_for_timeout(1200)
            node = next(item for item in design_model()["nodes"] if item["node_key"] == node_key)
            assert str(node["owner_position_id"]) == target_position, node
            ensure_sidebar()
            page.select_option("#bpPosition", original_position)
            page.click('#bpmnSidebar button:has-text("保存指标")')
            page.wait_for_timeout(1200)

            # L4 活动关联
            ensure_sidebar()
            original_activity = page.input_value("#bpActivity")
            activity_options = page.eval_on_selector_all(
                "#bpActivity option", "els => els.map(e => e.value).filter(Boolean)"
            )
            target_activity = next(
                (item for item in activity_options if item != original_activity), None
            )
            assert target_activity, activity_options
            page.select_option("#bpActivity", target_activity)
            page.click('#bpmnSidebar button:has-text("关联")')
            page.wait_for_timeout(1200)
            node = next(item for item in design_model()["nodes"] if item["node_key"] == node_key)
            assert str(node["process_arch_id"]) == target_activity, node
            ensure_sidebar()
            page.select_option("#bpActivity", original_activity)
            page.click('#bpmnSidebar button:has-text("关联")')
            page.wait_for_timeout(1200)

            # 活动级工具绑定（新增后通过 API 清理）
            ensure_sidebar()
            page.wait_for_selector("#bpToolCode", timeout=5000)
            tool_options = page.eval_on_selector_all(
                "#bpToolCode option", "els => els.map(e => e.value).filter(Boolean)"
            )
            tool_code = tool_options[0]
            page.select_option("#bpToolCode", tool_code)
            page.click('#bpmnSidebar button:has-text("绑定")')
            page.wait_for_timeout(1200)
            bound_tools = page.evaluate(
                """async ({pid, nodeKey}) => {
                  const t = localStorage.getItem('psm_token');
                  return await fetch('/api/v1/processes/' + pid + '/design/nodes/' +
                    nodeKey + '/tools', {headers: {Authorization: 'Bearer ' + t}})
                    .then(r => r.json());
                }""",
                {"pid": pid, "nodeKey": node_key},
            )
            assert any(item["tool_code"] == tool_code for item in bound_tools), bound_tools
            page.evaluate(
                """async ({pid, nodeKey, code}) => {
                  const t = localStorage.getItem('psm_token');
                  await fetch('/api/v1/processes/' + pid + '/design/nodes/' +
                    nodeKey + '/tools/' + encodeURIComponent(code),
                    {method: 'DELETE', headers: {Authorization: 'Bearer ' + t}});
                }""",
                {"pid": pid, "nodeKey": node_key, "code": tool_code},
            )

            # 活动级标准文件（创建后通过 API 清理）
            ensure_sidebar()
            page.click('#bpmnSidebar button:has-text("+ 新增标准文件")')
            page.wait_for_selector("#ndTitle", timeout=5000)
            page.fill("#ndTitle", "E2E 活动标准文件")
            page.click('#mFoot button:has-text("创建")')
            page.wait_for_timeout(1200)
            docs = page.evaluate(
                """async ({pid, nodeKey}) => {
                  const t = localStorage.getItem('psm_token');
                  return await fetch('/api/v1/process-documents?process_id=' + pid +
                    '&node_key=' + encodeURIComponent(nodeKey),
                    {headers: {Authorization: 'Bearer ' + t}}).then(r => r.json());
                }""",
                {"pid": pid, "nodeKey": node_key},
            )
            document = next(item for item in docs if item["title"] == "E2E 活动标准文件")
            assert document["node_key"] == node_key
            page.evaluate(
                """async (id) => {
                  const t = localStorage.getItem('psm_token');
                  await fetch('/api/v1/process-documents/' + id,
                    {method: 'DELETE', headers: {Authorization: 'Bearer ' + t}});
                }""",
                document["id"],
            )

            # 表单/规则状态区应已渲染
            assert "表单与分支规则" in page.inner_text("#bpmnSidebar")

            # 类型（TASK ↔ APPROVAL）
            ensure_sidebar()
            original_type = page.input_value("#bpNodeType")
            target_type = "APPROVAL" if original_type != "APPROVAL" else "TASK"
            page.select_option("#bpNodeType", target_type)
            page.click('#bpmnSidebar button:has-text("应用类型")')
            page.wait_for_timeout(1600)
            node = next(item for item in design_model()["nodes"] if item["node_key"] == node_key)
            assert node["node_type"] == target_type, node
            ensure_sidebar()
            page.select_option("#bpNodeType", original_type)
            page.click('#bpmnSidebar button:has-text("应用类型")')
            page.wait_for_timeout(1600)

            # 跨泳道移动
            ensure_sidebar()
            lane_options = page.eval_on_selector_all(
                "#bpNodeLane option", "els => els.map(e => e.value)"
            )
            original_lane = page.input_value("#bpNodeLane")
            target_lane = next((item for item in lane_options if item != original_lane), None)
            assert target_lane, lane_options
            page.select_option("#bpNodeLane", target_lane)
            page.click('#bpmnSidebar button:has-text("移动")')
            page.wait_for_timeout(1600)
            node = next(item for item in design_model()["nodes"] if item["node_key"] == node_key)
            assert node["lane"] == target_lane, node
            ensure_sidebar()
            page.select_option("#bpNodeLane", original_lane)
            page.click('#bpmnSidebar button:has-text("移动")')
            page.wait_for_timeout(1600)

            # 新增泳道（自动带默认活动）
            lane_name = f"E2E泳道{int(time.time() * 1000) % 100000}"
            lane_name2 = lane_name + "改"
            page.click('#view button:has-text("+ 泳道")')
            page.wait_for_selector("#uiDialogInput", timeout=5000)
            page.fill("#uiDialogInput", lane_name)
            page.click("#uiDialogOk")
            page.wait_for_timeout(2200)
            added = [item for item in design_model()["nodes"] if item["lane"] == lane_name]
            assert added, "新增泳道后没有默认活动"

            # 泳道改名
            page.evaluate(
                """(name) => {
                  const m = window.__bpmnSpike.modeler;
                  const lane = m.get('elementRegistry').getAll().find(
                    e => e.type === 'bpmn:Lane' && e.businessObject.name === name);
                  if (lane) m.get('selection').select(lane);
                }""",
                lane_name,
            )
            ensure_sidebar()
            page.wait_for_selector("#bpLaneName", timeout=5000)
            page.fill("#bpLaneName", lane_name2)
            page.click('#bpmnSidebar button:has-text("保存名称")')
            page.wait_for_timeout(1600)
            renamed = [item for item in design_model()["nodes"] if item["lane"] == lane_name2]
            assert renamed, "泳道改名后节点归属没有更新"

            # 连线标签/条件/概率
            flow = page.evaluate(
                """() => {
                  const m = window.__bpmnSpike.modeler;
                  const f = m.get('elementRegistry').getAll()
                    .find(e => e.type === 'bpmn:SequenceFlow');
                  if (!f) return null;
                  m.get('selection').select(f);
                  return {
                    source: f.businessObject.sourceRef.id,
                    target: f.businessObject.targetRef.id,
                  };
                }"""
            )
            assert flow, "流程没有连线"
            ensure_sidebar()
            page.wait_for_selector("#bpFlowProb", timeout=5000)
            assert "元素说明" in page.inner_text("#bpmnSidebar"), "连线属性缺少元素说明"
            assert "默认分支" in page.inner_text("#bpmnSidebar"), "连线属性缺少默认分支"
            assert "快捷键" in page.inner_text("#view"), "设计器缺少快捷键帮助入口"
            assert "评论" in page.inner_text("#view"), "设计器缺少评论入口"
            assert "路径模拟" in page.inner_text("#view"), "设计器缺少路径模拟入口"
            assert "补偿动作" in page.inner_text("#view"), "设计器缺少补偿动作入口"
            assert "决策表" in page.inner_text("#view"), "设计器缺少决策表入口"
            page.fill("#bpFlowLabel", "E2E标签")
            page.fill("#bpFlowCondition", "E2E条件")
            page.fill("#bpFlowProb", "0.55")
            page.click('#bpmnSidebar button:has-text("保存连线")')
            page.wait_for_timeout(2500)
            edge = next(
                item
                for item in design_model()["edges"]
                if item["source_key"] == flow["source"] and item["target_key"] == flow["target"]
            )
            assert edge["label"] == "E2E标签", edge
            assert edge["condition"] == "E2E条件", edge
            assert abs(edge["probability"] - 0.55) < 1e-6, edge

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
                page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      const nodes = [
                        {node_key: 'start', name: '开始', node_type: 'START', lane: '测试泳道'},
                        {node_key: 'task', name: '审批', node_type: 'APPROVAL', lane: '测试泳道',
                         owner_role: '测试岗', duration_minutes: 60, wait_minutes: 30,
                         cost: 10, rework_rate: 0, approval_levels: 1, is_value_added: false},
                        {node_key: 'end', name: '结束', node_type: 'END', lane: '测试泳道'},
                      ];
                      const edges = [
                        {source_key: 'start', target_key: 'task'},
                        {source_key: 'task', target_key: 'end'},
                      ];
                      await fetch('/api/v1/processes/' + pid + '/design', {
                        method: 'PUT',
                        headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                        body: JSON.stringify({nodes, edges}),
                      });
                      await fetch('/api/v1/execution/assignments', {
                        method: 'PUT',
                        headers: {Authorization: 'Bearer ' + t, 'Content-Type': 'application/json'},
                        body: JSON.stringify({process_id: pid, node_key: 'task',
                          role: null, org_unit_id: null, default_assignee_user_id: null,
                          due_hours: 2, escalation_hours: null, escalation_user_id: null}),
                      });
                    }""",
                    pid,
                )
                page.evaluate("(pid) => actions['designer.switch'](pid)", pid)
                page.wait_for_selector("#bpmnCanvas .djs-palette", state="visible", timeout=8000)
                page.wait_for_timeout(600)
                assert "草稿" in page.inner_text("#view"), page.inner_text("#view")[:200]

                assignments = page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      return await fetch('/api/v1/execution/assignments?process_id=' + pid,
                        {headers: {Authorization: 'Bearer ' + t}}).then(r => r.json());
                    }""",
                    pid,
                )
                assert any(
                    item["node_key"] == "task" and item["due_hours"] == 2 for item in assignments
                ), assignments

                page.click('#view button:has-text("版本历史")')
                page.wait_for_selector("#mask.show")
                assert "模型版本历史" in page.inner_text("#mTitle")
                assert "草稿" in page.inner_text("#mBody")
                close_modal()

                page.click('#view button:has-text("提交评审")')
                page.wait_for_selector("#uiDialogInput", timeout=5000)
                page.fill("#uiDialogInput", "E2E 评审")
                page.click("#uiDialogOk")
                page.wait_for_timeout(1400)
                assert "待评审" in page.inner_text("#view"), page.inner_text("#view")[:200]

                page.click('#view button:has-text("发布到运行时")')
                page.wait_for_selector("#uiDialogOk", timeout=5000)
                page.click("#uiDialogOk")
                page.wait_for_timeout(1600)
                assert page.inner_text("#pageTitle") == "流程执行", "发布后没有进入执行页"
                page.wait_for_selector("#mask.show", timeout=8000)
                assert "启动流程实例" in page.inner_text("#mTitle"), "发布后没有拉起启动弹窗"
                selected = page.eval_on_selector("#exProcess", "el => Number(el.value)")
                assert selected == pid, f"启动弹窗没有选中刚发布的流程：{selected} != {pid}"
                assert "start=1" not in page.url, "start 参数应在拉起弹窗后被消费"
                assert "process=" in page.url, f"执行页 URL 没有记录流程：{page.url}"
                page.screenshot(
                    path=str(out_dir / "interaction-designer-version.png"), full_page=True
                )
                close_modal()
                model = page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      return await fetch('/api/v1/processes/' + pid + '/design',
                        { headers: { Authorization: 'Bearer ' + t } }).then(r => r.json());
                    }""",
                    pid,
                )
                assert model["status"] == "PUBLISHED", model
            finally:
                page.evaluate(
                    """async (pid) => {
                      const t = localStorage.getItem('psm_token');
                      await fetch('/api/v1/process-map/' + pid,
                        { method: 'DELETE', headers: { Authorization: 'Bearer ' + t } });
                    }""",
                    pid,
                )
                page.evaluate(
                    "(pid) => go('designer', {params: {process: pid}, push: true})", fallback
                )
                page.wait_for_timeout(700)

        # 设计器「变更」页签：变更单 + 影响分析
        def designer_change_tab() -> None:
            goto("designer")
            pick_editable_design()
            page.click('#view .seg button:has-text("变更")')
            page.wait_for_timeout(700)
            view = page.inner_text("#view")
            assert "变更申请" in view, "设计器变更页未渲染"
            assert "重大变更需填写完整影响分析" in view, "变更页缺少门禁说明"
            page.click('#view button:has-text("+ 变更申请")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            modal = page.inner_text("#mBody")
            assert "变更类型" in modal and "影响级别" in modal, "变更弹窗缺类型/级别"
            assert "人员影响" in modal and "系统影响" in modal, "变更弹窗缺影响分析"
            assert "测试证据" in modal and "回退方案" in modal, "变更弹窗缺测试/回退"
            close_modal()
            page.wait_for_timeout(300)

            page.click('#view .seg button:has-text("权责")')
            page.wait_for_timeout(600)
            raci_view = page.inner_text("#view")
            assert "权责矩阵" in raci_view, "设计器权责页未渲染"
            assert "A 唯一负责" in raci_view or "缺少 A" in raci_view, "权责页缺少 A 状态"
            page.click('#view button:has-text("+ 事项权责")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            raci_modal = page.inner_text("#mBody")
            assert "事项 / 决策" in raci_modal and "RACI" in raci_modal, "权责弹窗缺字段"
            close_modal()
            page.wait_for_timeout(300)

        # 运营驾驶舱：总览 + KPI / 异常 / 工作量 / 过程挖掘 页签
        def monitor() -> None:
            goto("dashboard")
            page.wait_for_timeout(700)
            assert page.inner_text("#pageTitle") == "运营驾驶舱"
            assert "改善优先级" in page.inner_text("#view"), "总览缺少改善优先级"
            page.click('#view .cockpit-tabs button:has-text("KPI")')
            page.wait_for_timeout(1200)
            kpi_view = page.inner_text("#view")
            assert "流程健康度雷达" in kpi_view, "KPI 页签缺少雷达图"
            assert "整体达成率趋势" in kpi_view, "KPI 页签缺少整体趋势"
            assert "改善候选" in kpi_view, "KPI 页签缺少改善候选"
            assert "红/黄/绿" in kpi_view, "KPI 页签缺少红黄绿状态列"
            assert "全部类型" in kpi_view, "KPI 页签缺少类型筛选"

            # 定义卡：新建弹窗必须能填写口径、阈值与类型；编辑弹窗回填公式
            page.click('#view button:has-text("+ 新建 KPI")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            modal = page.inner_text("#mBody")
            assert "计算公式" in modal and "指标类型" in modal, (
                f"KPI 定义卡字段缺失：{modal[:160]!r}"
            )
            assert "红线" in modal and "绿线" in modal, "KPI 定义卡缺少红/黄/绿阈值"
            assert "生效版本" in modal and "数据来源系统" in modal, "KPI 定义卡缺少版本或来源"
            kinds = page.eval_on_selector_all(
                "#nkKind option", "els => els.map(e => e.textContent)"
            )
            assert {"结果", "过程", "健康度"} <= set(kinds), f"指标类型标签不完整：{kinds}"
            close_modal()
            page.wait_for_timeout(300)

            page.click('#view button:has-text("编辑") >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(500)
            edit_modal = page.inner_text("#mBody")
            assert "KPI 编码" in edit_modal and "计算公式" in edit_modal, "编辑弹窗未回填定义卡"
            assert page.locator("#nkCode").input_value(), "编辑弹窗缺少 KPI 编码"
            close_modal()
            page.wait_for_timeout(300)

            # 工作量：标准工时与产能必须能从标准需求算到负荷率
            page.click('#view .cockpit-tabs button:has-text("工作量")')
            page.wait_for_timeout(800)
            workload_view = page.inner_text("#view")
            assert "标准工时卡" in workload_view, "工作量页缺少标准工时卡"
            assert "产能与负荷" in workload_view, "工作量页缺少产能与负荷"
            assert "理论负荷率" in workload_view, "工作量页缺少负荷率"
            assert "能力基线" in workload_view, "工作量页缺少能力基线声明"
            assert "不用于个人" in workload_view, "工作量页缺少不用于个人考核声明"
            assert "tab=workload" in page.url, f"URL 没有记录监控页签：{page.url}"
            page.reload(wait_until="networkidle")
            page.wait_for_selector('#view .seg button[data-tab="workload"].on', timeout=8000)
            page.wait_for_timeout(600)
            assert "标准工时卡" in page.inner_text("#view"), "刷新没有恢复工作量页签"

            page.click('#view button:has-text("+ 标准工时")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            std_modal = page.inner_text("#mBody")
            assert "观测时间" in std_modal and "评定系数" in std_modal, "标准工时弹窗缺字段"
            assert "宽放率" in std_modal and "月频次" in std_modal, "标准工时弹窗缺口径字段"
            assert "不用于个人" in std_modal, "标准工时弹窗缺少使用边界声明"
            close_modal()
            page.wait_for_timeout(300)

            page.click('#view button:has-text("+ 产能")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            cap_modal = page.inner_text("#mBody")
            assert "出勤率" in cap_modal and "设备可用率" in cap_modal, "产能弹窗缺字段"
            close_modal()
            page.wait_for_timeout(300)

            page.click('#view .cockpit-tabs button:has-text("异常")')
            page.wait_for_timeout(600)
            # 异常台账在最后一张表，行内才有「处理」按钮
            page.click('#view button:has-text("处理") >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            body = page.inner_text("#mBody")
            assert "根因分析" in body, f"异常弹窗内容缺失：{body[:120]!r}"
            close_modal()
            page.wait_for_timeout(400)

        # 标准工时：观测记录 → 提交评审 → 审核通过
        def time_study_workflow() -> None:
            created = page.evaluate("""async () => {
                const t = localStorage.getItem('psm_token');
                const h = { Authorization: 'Bearer ' + t, 'Content-Type': 'application/json' };
                const acts = await fetch('/api/v1/process-map/flat?level=4',
                    { headers: h }).then(r => r.json());
                const pos = await fetch('/api/v1/positions',
                    { headers: h }).then(r => r.json());
                const res = await fetch('/api/v1/workload/standards', {
                    method: 'POST', headers: h,
                    body: JSON.stringify({
                        name: '自检用标准工时',
                        activity_id: acts[0].id,
                        position_id: pos[0].id,
                        method_description: '自检方法：取料→处理→放行',
                        source: 'TIME_STUDY',
                        observed_minutes: 10,
                        rating_factor: 1,
                        allowance_rate: 0.1,
                        sample_size: 0,
                        monthly_frequency: 1,
                    }),
                });
                return res.ok ? await res.json() : { error: await res.text() };
            }""")
            assert created.get("id"), created
            goto_cockpit_tab("工作量")
            page.wait_for_timeout(800)

            row = page.locator('#view tr:has-text("自检用标准工时")').first
            row.locator('button:has-text("样本")').click()
            page.wait_for_selector("#obsMinutes")
            modal = page.inner_text("#mBody")
            assert "至少 5 条有效样本" in modal, "样本弹窗缺少评审门槛说明"

            for index, minutes in enumerate((10, 10.5, 9.5, 10, 10), start=1):
                page.fill("#obsMinutes", str(minutes))
                page.click('#mBody button:has-text("+ 添加观测")')
                page.wait_for_function(
                    """(expected) => {
                        const body = document.getElementById('mBody');
                        return body && body.innerText.includes('样本 ' + expected + ' 条');
                    }""",
                    arg=index,
                    timeout=8000,
                )
                page.wait_for_selector("#obsMinutes")
            assert "样本 5 条" in page.inner_text("#mBody"), "样本量没有自动回算"

            page.click('#mFoot button:has-text("提交评审")')
            page.wait_for_selector("#mask.show")
            page.click("#uiDialogOk")
            page.wait_for_timeout(1200)

            row = page.locator('#view tr:has-text("自检用标准工时")').first
            assert "待审核" in row.inner_text(), "提交评审后状态不是待审核"
            row.locator('button:has-text("样本")').click()
            page.wait_for_selector("#obsMinutes")
            page.click('#mFoot button:has-text("通过")')
            page.wait_for_selector("#mask.show")
            page.fill("#uiDialogInput", "自检通过")
            page.click("#uiDialogOk")
            page.wait_for_timeout(1200)
            row = page.locator('#view tr:has-text("自检用标准工时")').first
            assert "已验证" in row.inner_text(), "审核通过后状态不是已验证"
            workload_view = page.inner_text("#view")
            assert "标准 vs 实际" in workload_view, "工作量看板缺少标准 vs 实际"
            assert "瓶颈岗位" in workload_view, "工作量看板缺少瓶颈岗位"
            assert "未来 3 个月缺口" in workload_view, "工作量看板缺少预测"

        # 数据治理：数据域/数据流登记与缺口概览
        def data_governance_view() -> None:
            goto("data")
            page.wait_for_timeout(800)
            view = page.inner_text("#view")
            assert "数据治理" in view and "数据域" in view and "数据流" in view, view[:200]
            assert "无所有者数据域" in view, "数据治理缺少缺口概览"

            page.click('#view button:has-text("+ 新建数据域")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            modal = page.inner_text("#mBody")
            assert "数据所有者" in modal and "数据管家" in modal, "数据域弹窗缺字段"
            close_modal()
            page.wait_for_timeout(300)

            page.click('#view button:has-text("+ 新建数据流")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            modal = page.inner_text("#mBody")
            assert "提取频率" in modal and "质量规则" in modal, "数据流弹窗缺字段"
            assert "关联流程" in modal and "主键" in modal, "数据流弹窗缺关联字段"
            close_modal()
            page.wait_for_timeout(300)

        # 资源中心：知识库已并入工具箱的「全部资源」，验证管理入口、推荐与详情
        def knowledge() -> None:
            goto("toolbox")
            page.wait_for_timeout(900)
            page.click('#view button[data-act="toolbox.section"][data-section="resources"]')
            page.wait_for_timeout(1400)
            view = page.inner_text("#view")
            assert "全部资源" in view and "资源类型" in view, "全部资源区块没有展开"
            assert "归档候选" in view, "管理员资源区缺少归档候选"
            assert "使用效果" in view, "管理员资源区缺少使用效果统计"
            assert "场景管理" in view and "推荐日志" in view, "管理员缺少运营入口"

            page.click('#view button[data-act="knowledge.manageScenarios"]')
            page.wait_for_selector("#mask.show", timeout=5000)
            page.wait_for_timeout(1200)
            scenario_body = page.inner_text("#mask")
            assert "场景字典管理" in scenario_body, f"场景管理弹窗未渲染：{scenario_body[:200]!r}"
            close_modal()
            page.wait_for_timeout(400)

            page.click('#view button[data-act="knowledge.showRecommendLogs"]')
            page.wait_for_selector("#mask.show", timeout=5000)
            page.wait_for_timeout(1000)
            log_body = page.inner_text("#mask")
            assert "推荐解释日志" in log_body, f"推荐日志弹窗未渲染：{log_body[:200]!r}"
            close_modal()
            page.wait_for_timeout(400)

            # 场景 → ① 推荐：点「责任不清」应切回问题匹配并带出案例/模板
            page.click('#view .kb-pain[data-scenario="RACI"]')
            page.wait_for_timeout(1600)
            view = page.inner_text("#view")
            assert "匹配结果" in view, "场景匹配没有切回 ①"
            assert "RACI" in view, "责任不清场景没有推荐 RACI"
            assert "配套案例 / 模板" in view, "场景匹配没有带出配套资源"

            page.click('#view .kb-reco-item button[data-act="knowledge.open"] >> nth=0')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(900)
            body = page.inner_text("#mBody")
            assert "使用证据" in body, f"知识详情缺少证据区：{body[:160]!r}"
            assert "适用条件" in body and "不适用" in body, "知识详情缺少适用/反证条件"
            close_modal()
            page.wait_for_timeout(700)

            page.fill("#toolQ", "跨部门互相推诿、权责不清")
            page.click('#view button[data-act="toolbox.match"]')
            page.wait_for_timeout(1500)
            assert "匹配结果" in page.inner_text("#view"), "快速匹配没有推荐结果"

            page.click('#view button[data-act="knowledge.new"]')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(600)
            modal = page.inner_text("#mask")
            assert "入库前自检" in modal and "提交审核" in modal, "新建资源缺少求真审核门槛"
            assert "适用场景" in modal and "反证" in modal, "新建资源缺少场景/反证字段"
            close_modal()
            page.wait_for_timeout(600)

            # 制度中心深链：工具箱 → deliverables?tab=document，刷新后仍停在标准文件页签
            page.click('#view [data-act="knowledge.goDocuments"] >> nth=0')
            page.wait_for_timeout(1000)
            assert page.inner_text("#pageTitle") == "交付物与模板库", "制度中心跳转失败"
            assert "tab=document" in page.url, f"制度中心没有写入 tab URL：{page.url}"
            assert "流程标准文件" in page.inner_text("#view .tabs button.on"), "未落在标准文件页签"
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1000)
            assert "流程标准文件" in page.inner_text("#view .tabs button.on"), "刷新后页签丢失"

        # 知识库：按阶段选择后，左侧折叠互斥，中间推荐只保留该阶段命中项
        # 工具箱：按阶段筛选后互斥展开 ②，① 折叠
        def knowledge_stage_filter() -> None:
            goto("toolbox")
            page.wait_for_timeout(700)
            page.click('#view .kb-nav-fold summary:has-text("按阶段")')
            page.wait_for_timeout(200)
            page.click("#view .kb-stage-link >> nth=1")
            page.wait_for_timeout(1400)
            assert "stage=" in page.url, f"阶段选择没有写入 URL：{page.url}"
            details = page.locator("#view .kb-nav-fold")
            assert details.count() == 4, "左侧导航不是四个折叠区"
            assert not details.nth(0).evaluate("el => el.open"), "选择阶段后「按问题」应折叠"
            assert details.nth(1).evaluate("el => el.open"), "选择阶段后「按阶段」应展开"
            view = page.inner_text("#view")
            assert "资源类型" in view and "案例 / 模板" in view, (
                f"阶段筛选没有展开全部资源：{view[:200]}"
            )
            assert page.locator("#toolQ").count() == 0, "选择阶段后 ① 应折叠"

        # 项目组合：阶段筛选下拉必须显示阶段名称
        def projects_stage_names() -> None:
            goto("projects")
            labels = page.eval_on_selector_all(
                '#view select[data-key="stage"] option', "els => els.map(e => e.textContent)"
            )
            assert any("识别与优先级排序" in item for item in labels), (
                f"改善项目阶段名缺失：{labels}"
            )
            assert any("立项定界" in item for item in labels), f"体系落地阶段名缺失：{labels}"

        # 工具箱：工具卡的「相关案例/模板」应切到 ② 并按工具过滤
        def knowledge_tool_jump() -> None:
            goto("toolbox")
            page.wait_for_timeout(900)
            page.click('#view .kb-pain[data-scenario="RACI"]')
            page.wait_for_timeout(1500)
            btn = page.locator('#view .tb-card button[data-act="toolbox.goKnowledge"]').first
            assert btn.count(), "工具卡缺少「相关案例/模板」入口"
            btn.click()
            page.wait_for_timeout(1400)
            assert "资源类型" in page.inner_text("#view"), "没有切到全部资源"
            assert "rtool=" in page.url, f"关联工具筛选没有写入 URL：{page.url}"
            assert "只显示关联工具" in page.inner_text("#view"), "没有显示关联工具筛选提示"

        # 工作流步骤 → 工具箱：保留 step 上下文并可直接记录使用证据
        def knowledge_step_context() -> None:
            goto_workflow_tab("五阶段步骤")
            page.click("#view .step >> nth=0")
            page.wait_for_selector("#wfRec h3", timeout=8000)
            link = page.locator('#wfRec .kb-step-item button:has-text("去方法论工具箱")')
            assert link.count(), "步骤推荐知识缺少「去方法论工具箱」入口"
            link.first.click()
            page.wait_for_timeout(1600)
            assert page.inner_text("#pageTitle") == "方法论工具箱", "没有跳转到工具箱"
            view = page.inner_text("#view")
            assert "用到 1.1" in view, f"工具箱没有步骤上下文按钮：{view[:200]}"
            page.click('#view .kb-reco-item button[data-act="knowledge.applyStep"] >> nth=0')
            page.wait_for_selector("#mask.show")
            body = page.inner_text("#mBody")
            assert "关联工作流步骤" in body and "1.1" in body, body[:200]
            close_modal()
            page.wait_for_timeout(400)

        def project_gantt() -> None:
            goto("projects")
            page.click("#view .project-open >> nth=0")
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
            goto_cockpit_tab("异常")
            page.click("text=+ 登记异常")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(500)
            page.fill("#neTitle", "自检用临时异常")
            page.fill("#neOwner", "自检员")
            page.click("#mFoot .btn-p")
            page.wait_for_timeout(1600)
            assert "已登记" in page.inner_text("#toast"), page.inner_text("#toast")
            assert "自检用临时异常" in page.inner_text("#view")

            # 异常台账 → 改善项目：服务端生成草稿后直接打开项目详情
            row = page.locator('#view tr:has-text("自检用临时异常")').first
            row.locator('button:has-text("转改善")').click()
            page.wait_for_timeout(1800)
            assert page.inner_text("#pageTitle") == "流程项目组合", "异常转改善没有进入项目组合"
            assert "project=" in page.url, f"URL 没有记录改善项目：{page.url}"
            page.wait_for_selector("#mask.show", timeout=8000)
            assert "改善项目卡" in page.inner_text("#mBody"), "改善项目详情缺少改善项目卡"
            close_modal()

        # 直接打开视图路径：服务端返回前端入口，启动后按路径进入对应视图
        def direct_view_url() -> None:
            page.goto(base + "/start", wait_until="networkidle")
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "开始使用", (
                f"直接打开 /start 未进入启动页：{page.inner_text('#pageTitle')}"
            )
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
            goto_cockpit_tab("KPI")
            page.select_option("#themeSel", "slate")
            page.wait_for_timeout(400)
            assert page.evaluate("document.documentElement.dataset.theme") == "slate"
            page.screenshot(path=str(out_dir / "theme-slate.png"), full_page=True)
            page.select_option("#themeSel", "default")
            page.wait_for_timeout(300)
            assert page.evaluate("document.documentElement.dataset.theme") == "default"

        # 左侧主导航：折叠只留图标、刷新保持、展开后不影响导航
        def main_nav_collapse() -> None:
            goto("dashboard")
            if page.evaluate("document.documentElement.classList.contains('nav-collapsed')"):
                page.click("#navCollapse")
                page.wait_for_timeout(300)
            assert page.locator(".side").bounding_box()["width"] > 200
            page.click("#navCollapse")
            page.wait_for_timeout(300)
            assert page.evaluate("document.documentElement.classList.contains('nav-collapsed')")
            assert page.locator(".side").bounding_box()["width"] < 80
            assert not page.locator(".nav .grp").first.is_visible()
            assert not page.locator(".nav a .lbl").first.is_visible()
            assert page.get_attribute('.nav a[data-view="map"]', "title") == "企业流程地图", (
                "折叠后缺少导航提示"
            )

            page.reload(wait_until="networkidle")
            page.wait_for_timeout(1200)
            assert page.evaluate("document.documentElement.classList.contains('nav-collapsed')"), (
                "刷新后没有保持折叠状态"
            )

            page.click("#navCollapse")
            page.wait_for_timeout(300)
            assert page.locator(".side").bounding_box()["width"] > 200
            page.evaluate("() => localStorage.removeItem('pms_nav_collapsed')")

        # 驾驶舱入口：快捷链接、指标卡、阶段行都要真的能跳转
        def dashboard_entries() -> None:
            goto("dashboard")
            page.wait_for_selector("#view .kpi.stat", timeout=8000)
            assert "我的当前推进" in page.inner_text("#view"), "驾驶舱缺少当前推进卡"
            continue_btn = page.locator('#view button[data-act="dashboard.openProject"]')
            if continue_btn.count():
                continue_btn.first.click()
                page.wait_for_selector("#mask.show")
                page.wait_for_timeout(1400)
                assert "概览" in page.inner_text("#mBody"), "继续推进未打开项目详情"
                close_modal()
            else:
                page.click('#view a:has-text("项目组合")')
                page.wait_for_timeout(700)
                assert page.inner_text("#pageTitle") == "流程项目组合"

            goto("dashboard")
            page.click("#view a.kpi.stat >> nth=0")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "流程项目组合"
            assert page.locator('#view select[data-key="status"]').input_value() == "ACTIVE"
            assert "status=ACTIVE" in page.url, f"URL 没有记录筛选：{page.url}"

            goto("dashboard")
            page.click("#view a.stage-row >> nth=0")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "流程项目组合"
            assert page.locator('#view select[data-key="stage"]').input_value() == "1"
            assert "stage=1" in page.url, f"URL 没有记录阶段筛选：{page.url}"

            goto("dashboard")
            page.click("#view .card:has(h3:has-text('改善优先级')) .project-open >> nth=0")
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "企业流程地图"
            page.wait_for_selector("#mask.show")
            assert "综合优先级得分" in page.inner_text("#mask")
            close_modal()

            goto("dashboard")
            page.click("#view a.kpi.stat >> nth=2")
            page.wait_for_timeout(900)
            assert page.inner_text("#pageTitle") == "运营驾驶舱"
            assert "异常事件台账" in page.inner_text("#view")

        # 战略目标：年度目标与「目标 → 流程 → KPI」承接
        def strategy_view() -> None:
            goto("strategy")
            page.wait_for_timeout(800)
            view = page.inner_text("#view")
            assert "战略目标" in view and "年度目标" in view, "战略目标页未渲染"
            assert "已承接流程" in view, "战略目标页缺少承接汇总"
            page.click('#view button:has-text("+ 新建目标")')
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(400)
            modal = page.inner_text("#mBody")
            assert "目标名称" in modal and "目标值" in modal, "战略目标弹窗缺字段"
            assert "来源文件" in modal and "基线值" in modal, "战略目标弹窗缺口径字段"
            close_modal()
            page.wait_for_timeout(300)

            # 战略目标 → 选流程 / 立项：流程与目标值一起带进立项向导
            btn = page.locator('#view button[data-act="strategy.initiate"]')
            assert btn.count(), "战略目标没有「选流程 / 立项」入口"
            btn.first.click()
            page.wait_for_selector("#siProcess", timeout=8000)
            assert page.locator("#siProcess option").count() >= 1, "没有可选的 L3/L4 流程"
            page.click('#mFoot button[data-act="strategy.submitInitiate"]')
            page.wait_for_timeout(1400)
            assert page.inner_text("#pageTitle") == "流程项目组合", "没有进入立项向导"
            page.wait_for_selector("#npName", timeout=8000)
            assert "new_process=" in page.url and "new_objective=" in page.url, page.url
            wizard = page.inner_text("#mBody")
            assert "承接战略目标" in wizard, "立项向导没有带入战略目标"
            assert page.locator("#npMetric").input_value(), "立项向导没有预填指标名称"
            assert page.locator("#npTarget").input_value(), "立项向导没有预填目标值"
            close_modal()
            page.wait_for_timeout(300)

        def start_view() -> None:
            goto("start")
            page.wait_for_timeout(900)
            view = page.inner_text("#view")
            assert "开始使用" in view and "唯一主入口" in view, "启动向导未渲染"
            assert page.locator("#view .tl-step").count() == 9, "九阶段时间轴不完整"
            assert page.locator("#view .tl-step.current").count() == 1, "时间轴没有当前阶段"
            assert page.locator("#view .tl-step.done").count() >= 1, "时间轴没有已完成阶段"
            assert "当前" in page.inner_text("#view .start-timeline")
            assert page.locator("#view .start-shell").count() == 1, "开始页没有三栏布局"
            assert page.locator("#view .start-nav-item").count() == 9, "左侧应是 9 个阶段"
            assert page.locator("#view .start-nav-item.on").count() == 1, "左侧没有唯一选中阶段"
            assert "Q1 要什么" not in view and "地图层" not in view, "八问不该再出现在开始页"
            assert "当前位置" in view, "右侧缺少当前位置"
            assert "前 8 个阶段" in view and "评审与固化" in view, "启动页缺少上线范围"
            tip = page.locator("#view .page-head .metric-help.has-tip")
            assert tip.count() == 1, "开始页没有把计数口径收进说明"
            tip_text = tip.first.get_attribute("data-tip") or ""
            assert "全公司计数" in tip_text and "这次先不做" in tip_text, tip_text
            gate = page.evaluate(
                """async () => {
                    const token = localStorage.getItem('psm_token');
                    const res = await fetch('/api/v1/start/status', {
                        headers: { Authorization: 'Bearer ' + token },
                    });
                    return res.ok ? await res.json() : null;
                }"""
            )
            view = page.inner_text("#view")
            if gate and gate["pilot_confirmed"]:
                assert "已确认上线" in view and "撤销确认" in view
            elif gate and gate["pilot_gate_open"]:
                assert "确认首次上线" in view
            else:
                assert "还差 " in view and "个阶段" in view, "启动页缺少上线缺口说明"

            view = page.inner_text("#view")
            has_current = page.locator("#view .start-current").count() == 1
            assert has_current or "九个阶段都齐了" in view or "能做的都做了" in view, (
                "启动页没有当前步"
            )
            assert page.locator("#view .start-current").count() <= 1, "不应一次展开多步"

            if has_current:
                view = page.inner_text("#view")
                assert "这一步要留下什么" in view, "启动向导缺少证据面板"
                jumps = page.locator("#view .start-current button.ev-jump")
                assert jumps.count() >= 1, "证据计数不能打开记录"
                assert jumps.first.get_attribute("data-view"), "证据计数没有落点页面"
                assert "已经有的" in view and ("还缺的" in view or "建议补上" in view), (
                    "证据面板缺少缺项"
                )
                # 跳过 = 未验证，且可以取消
                skip_button = page.locator('#view .start-current button[data-act="start.skip"]')
                key = skip_button.first.get_attribute("data-key")
                skipped_keys.append(key)
                skip_button.first.click()
                page.wait_for_selector("#mask.show")
                page.click("#uiDialogOk")
                page.wait_for_timeout(1400)
                assert page.locator("#view .tl-step.skipped").count() >= 1, (
                    "跳过步骤未在时间轴标记为未验证"
                )
                assert "未验证" in page.inner_text("#view .start-timeline")
                # 恢复入口在右侧折叠列表
                page.locator("#view details.start-fold summary").first.click()
                page.wait_for_timeout(300)
                unskip = page.locator(f'#view button[data-act="start.unskip"][data-key="{key}"]')
                assert unskip.count(), "跳过后的步骤没有取消跳过入口"
                unskip.first.click()
                page.wait_for_selector("#mask.show")
                page.click("#uiDialogOk")
                page.wait_for_timeout(1400)
                skipped_keys.remove(key)
                assert page.locator("#view .tl-step.skipped").count() == 0, "取消跳过后仍是未验证"

        def process_card_view() -> None:
            goto("process_card")
            page.wait_for_timeout(1400)
            view = page.inner_text("#view")
            assert "流程卡" in view, "流程卡未渲染"
            assert "对象 360" in view, "流程卡没有切回对象 360 定位"
            assert "试点落地" in view, "流程卡缺少当前试点层摘要"
            assert page.locator("#view .pc-nav-item").count() >= 10, "流程卡左侧模块导航不完整"
            assert page.locator("#view .pc-module").count() == 1, "中间应只展示一个模块详情"
            assert page.locator("#view .pc-related-col").count() == 1, "右侧操作/相关栏缺失"
            page.locator('#view .pc-nav-item:has-text("KPI")').first.click()
            page.wait_for_function(
                """() => document.querySelector('#view .pc-main')?.innerText.includes('KPI')""",
                timeout=5000,
            )
            assert "KPI" in page.inner_text("#view .pc-main"), "点击左侧条目未切换中间详情"
            for marker in (
                "战略承接",
                "权责矩阵",
                "制度与标准",
                "流程模型",
                "工作量与产能",
                "KPI",
                "变更",
                "改善",
                "治理待办",
                "成熟度",
                "L5 任务",
            ):
                assert marker in view, f"流程卡缺少「{marker}」区块"
            options = page.eval_on_selector_all(
                "#view select.sel option", "els => els.map(e => e.value).filter(Boolean)"
            )
            if len(options) > 1:
                page.select_option("#view select.sel", value=options[1])
                page.wait_for_timeout(1200)
                assert "流程卡" in page.inner_text("#view")
                assert "process=" in page.url, f"URL 没有记录流程卡流程：{page.url}"
                selected = page.eval_on_selector("#view select.sel", "el => el.value")
                page.reload(wait_until="networkidle")
                page.wait_for_timeout(1200)
                assert page.eval_on_selector("#view select.sel", "el => el.value") == selected, (
                    "刷新后没有恢复同一条流程"
                )
                assert "流程卡" in page.inner_text("#view")

        # 返回来源与固定主线：跨页跳转可回来源，任意页可回 0→1 主线
        def navigation_origin_and_mainline() -> None:
            goto("process_card")
            page.wait_for_timeout(1200)
            entry = page.locator(
                '#view button[data-act="process_card.pilot"], '
                '#view button[data-act="process_card.goPilot"], '
                '#view button[data-act="process_card.go"][data-view="pilot"]'
            ).first
            assert entry.count(), "流程卡没有进入十层核对的入口"
            entry.click()
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "十层核对"
            assert page.is_visible("#originBack"), "跨页跳转后没有返回来源"
            assert "返回 流程卡" in page.inner_text("#originBack")
            if "process=" in page.url:
                process_id = page.url.split("process=")[1].split("&")[0]
                page.click('#view button[data-act="pilot.newPath"]')
                page.wait_for_selector("#plProcess")
                assert page.input_value("#plProcess") == process_id, "十层核对没有带入来源流程"
                close_modal()
            page.click("#originBack")
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "流程卡"
            assert not page.is_visible("#originBack"), "返回来源后返回按钮应隐藏"

            page.click('#originBar button[data-act="shell.mainline"]')
            page.wait_for_timeout(1200)
            assert page.inner_text("#pageTitle") == "开始使用", "主线按钮没有回到唯一主入口"
            assert not page.is_visible("#originBack")

        def select_click_stable() -> None:
            goto("projects")
            page.wait_for_timeout(700)
            sel = page.locator('#view select[data-key="status"]')
            assert sel.count() == 1, "项目筛选下拉不存在"
            sel.click()
            page.wait_for_timeout(300)
            assert sel.evaluate("el => el.isConnected"), "点击下拉后控件被重渲染（一闪而过）"
            page.keyboard.press("Escape")

        def authorization_view() -> None:
            goto("authorization")
            page.wait_for_timeout(900)
            view = page.inner_text("#view")
            assert "授权矩阵" in view and "已生效规则" in view, "授权矩阵未渲染"

            page.click('#view button:has-text("+ 新建规则")')
            page.wait_for_selector("#mask.show")
            page.fill("#azTitle", "自检用授权规则")
            page.fill("#azMatter", "自检用关键事项")
            page.select_option("#azCategory", "C")
            page.fill("#azApproverLabel", "自检审批人")
            page.fill("#azException", "自检例外路径")
            page.fill("#azEvidence", "自检审批证据")
            page.click('#mFoot button:has-text("创建")')
            page.wait_for_timeout(1200)
            assert "自检用授权规则" in page.inner_text("#view"), "新建规则未出现在列表"

            row = page.locator('#view tr:has-text("自检用授权规则")').first
            row.locator('button:has-text("生效")').click()
            page.wait_for_selector("#mask.show")
            page.click("#uiDialogOk")
            page.wait_for_timeout(1200)
            assert "已生效" in page.inner_text("#view"), "规则未生效"

            page.click('#view .seg button:has-text("例外台账")')
            page.wait_for_timeout(300)
            page.click('#view button:has-text("+ 申请例外")')
            page.wait_for_selector("#mask.show")
            page.fill("#aeTitle", "自检用例外")
            page.fill("#aeReason", "自检原因")
            page.fill("#aeExpires", "2027-12-31")
            page.click('#mFoot button:has-text("提交申请")')
            page.wait_for_timeout(1200)
            page.click('#view .seg button:has-text("例外台账")')
            page.wait_for_timeout(300)
            assert "自检用例外" in page.inner_text("#view"), "例外申请未出现在台账"

            exc_row = page.locator('#view tr:has-text("自检用例外")').first
            exc_row.locator('button:has-text("批准")').click()
            page.wait_for_selector("#mask.show")
            page.fill("#uiDialogInput", "自检批准")
            page.click("#uiDialogOk")
            page.wait_for_timeout(1200)
            page.click('#view .seg button:has-text("例外台账")')
            page.wait_for_timeout(300)
            assert "自检用例外" in page.inner_text("#view"), "例外行不见了"
            assert "已批准" in page.inner_text("#view"), "例外未批准"

        def pilot_view() -> None:
            goto("pilot")
            page.wait_for_timeout(1200)
            assert "十层核对" in page.inner_text("#view"), "十层核对未渲染"

            if page.locator("#view .pilot-layer").count() == 0:
                page.click('#view button:has-text("+ 新建路径")')
                page.wait_for_selector("#mask.show")
                assert page.locator("#plName").count() == 0, "不应再要求另起路径名"
                options = page.eval_on_selector_all(
                    "#plProcess option",
                    "els => els.map(e => ({value: e.value, text: e.textContent}))"
                    ".filter(e => e.value)",
                )
                assert options, "没有可选的 L3/L4 流程"
                page.select_option("#plProcess", value=options[0]["value"])
                page.click('#mFoot button:has-text("创建")')
                page.wait_for_timeout(1400)
                view = page.inner_text("#view")
                # 选项文案形如「L3 CODE 名称」
                process_name = options[0]["text"].split(" ", 2)[-1].strip()
                assert process_name and process_name in view, (
                    f"十层路径未按流程名展示：{options[0]['text']!r}"
                )
            assert page.locator("#view .pilot-workspace button.ev-jump").count() >= 1, (
                "十层退出门计数不能打开证据"
            )
            assert page.locator("#view .pilot-layer").count() == 10, "十层导航不完整"
            assert page.locator("#view .pilot-side .pilot-layer").count() == 10, (
                "十层导航没有落在左侧栏"
            )

            page.click('#view .pilot-layer[data-layer="4"]')
            page.wait_for_timeout(900)
            view = page.inner_text("#view")
            assert "制度与授权设计" in view and "退出门" in view, "第4层工作区未展开"
            assert "制度、授权与例外（本流程范围）" in view, "第4层缺少制度/授权工作区"
            assert "layer=4" in page.url, f"URL 没有记录当前层：{page.url}"

            page.go_back()
            page.wait_for_selector('#view .pilot-layer.on[data-layer="1"]', timeout=8000)
            page.wait_for_timeout(500)
            back_view = page.inner_text("#view")
            assert "制度、授权与例外（本流程范围）" not in back_view, "后退没有回到上一层"

            page.go_forward()
            page.wait_for_selector('#view .pilot-layer.on[data-layer="4"]', timeout=8000)
            page.wait_for_timeout(500)
            assert "制度、授权与例外（本流程范围）" in page.inner_text("#view"), "前进没有恢复第4层"
            page.reload(wait_until="networkidle")
            page.wait_for_selector('#view .pilot-layer.on[data-layer="4"]', timeout=8000)
            page.wait_for_timeout(500)
            assert "制度、授权与例外（本流程范围）" in page.inner_text("#view"), "刷新没有恢复第4层"
            page.screenshot(path=str(out_dir / "pilot-layer4.png"), full_page=True)

            page.click('#view button:has-text("+ 新增待办")')
            page.wait_for_selector("#mask.show")
            page.fill("#ptTitle", "自检用待办")
            page.click('#mFoot button:has-text("创建")')
            page.wait_for_timeout(1200)
            assert "自检用待办" in page.inner_text("#view"), "待办未出现"

            page.click('#view button:has-text("+ 新增异常")')
            page.wait_for_selector("#mask.show")
            page.fill("#piTitle", "自检用阻断异常")
            page.select_option("#piSeverity", "BLOCKER")
            page.click('#mFoot button:has-text("创建")')
            page.wait_for_timeout(1200)
            assert "自检用阻断异常" in page.inner_text("#view"), "异常未出现"
            assert "被阻断" in page.inner_text("#view"), "阻断异常未让本层变为被阻断"

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
                page.click('#mFoot button:has-text("挂起实例")')
                page.wait_for_selector("#uiDialogInput", timeout=5000)
                page.fill("#uiDialogInput", "E2E 挂起")
                page.click("#uiDialogOk")
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
            page.click("#view .map-open >> nth=2")
            page.wait_for_timeout(600)
            page.click("#view .map-row:has-text('L2-003') .map-open")
            page.wait_for_timeout(600)
            row = page.locator("#view .map-row:has-text('L3-032')").first
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

        def strategy_open_process() -> None:
            goto("strategy")
            page.wait_for_timeout(900)
            btn = page.locator('#view button[data-act="strategy.openProcess"]').first
            assert btn.count(), "战略目标没有「看流程」入口"
            level = int(btn.get_attribute("data-level") or 0)
            btn.click()
            page.wait_for_timeout(1400)
            if level >= 3:
                # L3/L4：进入单流程 360，而不是让用户在地图里再找一次。
                assert page.inner_text("#pageTitle") == "流程卡"
                assert "战略承接" in page.inner_text("#view"), "流程卡没有渲染战略承接区块"
            else:
                assert page.inner_text("#pageTitle") == "企业流程地图"
                page.wait_for_selector("#mask.show", timeout=8000)
                assert "流程" in page.inner_text("#mask"), "没有按目标承接的流程打开详情"
                close_modal()

        def designer_to_execution() -> None:
            goto("designer")
            pick_editable_design()
            page.click('#view a:has-text("去流程执行")')
            page.wait_for_timeout(1600)
            assert page.inner_text("#pageTitle") == "流程执行"
            assert "任务时限" in page.inner_text("#view"), "设计器没有把流程带进执行配置"

        def project_to_execution() -> None:
            goto("projects")
            page.click("#view .project-open >> nth=0")
            page.wait_for_selector("#mask.show")
            page.wait_for_timeout(1100)
            assert "project=" in page.url, f"URL 没有记录项目：{page.url}"
            page.reload(wait_until="networkidle")
            page.wait_for_selector("#mask.show", timeout=8000)
            page.wait_for_selector("#mBody .tabs", timeout=8000)
            page.wait_for_timeout(600)
            assert "概览" in page.inner_text("#mBody"), "刷新没有恢复项目详情"
            btn = page.locator('#mFoot button[data-act="projects.openExecution"]')
            assert btn.count(), "项目详情没有「去流程执行」入口"
            btn.first.click()
            page.wait_for_timeout(1600)
            assert page.inner_text("#pageTitle") == "流程执行"
            assert "任务时限" in page.inner_text("#view"), "执行页没有落到当前流程的配置页签"

        check("战略目标→看流程", strategy_open_process)
        check("设计器→流程执行", designer_to_execution)
        check("项目详情→流程执行", project_to_execution)
        check("地图下钻", map_drill)
        check("地图「进入」按钮", map_enter_button)
        check("架构树计数", map_tree_counts)
        check("流程详情配套文件入口", map_documents_entry)
        check("对标框架切换", benchmark_switch)
        check("交互原语：确认/输入对话框", ui_dialogs)
        check("PCF 分类浏览（层级/双语/指标）", pcf_browser)
        check("从 PCF 生成草稿向导（预览）", pcf_draft_wizard)
        check("PCF 1+3+10 引导", pcf_guided_wizard)
        check("主题切换", theme_switch)
        check("主导航折叠", main_nav_collapse)
        check("驾驶舱入口", dashboard_entries)
        check("战略目标承接", strategy_view)
        check("开始使用九步向导", start_view)
        check("流程卡聚合视图", process_card_view)
        check("返回来源与固定主线", navigation_origin_and_mainline)
        check("下拉选择稳定", select_click_stable)
        check("授权矩阵与例外台账", authorization_view)
        check("十层核对与第4层工作区", pilot_view)
        check("指标口径提示", metric_help)
        check("通知中心", notifications)
        check("工作流项目工作台", workflow_workbench)
        check("工作流步骤详情", workflow_step_modal)
        check("步骤推荐工具与模板", workflow_step_recommendations)
        check("步骤页过滤工具箱", step_to_filtered_toolbox)
        check("方法论匹配引擎", workflow_recommend)
        check("项目详情四页签 + 步骤改状态", project_detail_tabs)
        check("工作流推进动作闭环", project_step_actions)
        check("立项向导内嵌工具详情", wizard_tool_modal)
        check("立项向导（真实入库）", project_wizard)
        check("工具箱详情 + 按问题找工具", toolbox)
        check("交付物关联流程模型", deliverable_model_link)
        check("交付物与模板库", deliverables_view)
        check("交付物新建版本", deliverable_new_version)
        check("交付物上传（真实入库）", deliverables_upload)
        check("组织与人员管理界面", admin_orgs)
        check("草图 draw.io 消息协议", sketch_drawio_protocol)
        check("设计器只读调色板可见可折叠", designer_readonly_palette)
        check("设计器 XML 纯函数特征测试", designer_xml_pure_functions)
        check("设计器改节点并重算", designer_edit_node)
        check("设计器专业 BPMN 画布（bpmn-js）", designer_bpmn_spike)
        check("设计器 bpmn-js 属性补全", designer_bpmn_properties)
        check("设计器版本治理（草稿→评审→发布）", designer_version_governance)
        check("设计器变更申请与影响分析", designer_change_tab)
        check("监控异常处理弹窗", monitor)
        check("标准工时观测与评审", time_study_workflow)
        check("数据治理数据域与数据流", data_governance_view)

        def legacy_knowledge_redirect() -> None:
            page.evaluate(
                "() => go('knowledge', {params: {type: 'CASE', scenario: 'RACI'}, skipOrigin: true})"
            )
            page.wait_for_timeout(1400)
            assert page.inner_text("#pageTitle") == "方法论工具箱", "旧知识库链接没有重定向"
            assert page.url.split("#")[-1].startswith("toolbox"), (
                f"URL 没有切到 toolbox：{page.url}"
            )
            view = page.inner_text("#view")
            assert "匹配结果" in view or "全部资源" in view, "重定向后页面没有内容"

        check("旧知识库链接重定向", legacy_knowledge_redirect)
        check("工具箱阶段筛选（互斥展开）", knowledge_stage_filter)
        check("项目组合阶段名称", projects_stage_names)
        check("全部资源 + 详情 + 快速匹配", knowledge)
        check("工具卡 → 关联案例/模板", knowledge_tool_jump)
        check("工作流 → 工具箱步骤上下文", knowledge_step_context)
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
              async (keys) => {
                const t = localStorage.getItem('psm_token');
                const h = { Authorization: 'Bearer ' + t };
                const out = [];
                for (const k of (keys || [])) {
                  await fetch('/api/v1/start/steps/' + k + '/skip', { method: 'DELETE', headers: h });
                  out.push('startup-skip:' + k);
                }
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
                const authRules = await fetch('/api/v1/authorization/rules', { headers: h }).then(r => r.json());
                for (const r of authRules) {
                  if (r.title.includes('自检用')) {
                    await fetch('/api/v1/authorization/rules/' + r.id, {
                      method: 'PATCH',
                      headers: { ...h, 'Content-Type': 'application/json' },
                      body: JSON.stringify({ title: r.title }),
                    });
                    await fetch('/api/v1/authorization/rules/' + r.id, {
                      method: 'DELETE', headers: h,
                    });
                    out.push('authorization-rule:' + r.code);
                  }
                }
                const standards = await fetch(
                  '/api/v1/workload/standards?include_retired=true', { headers: h }
                ).then(r => r.json());
                for (const s of standards) {
                  if (s.name.includes('自检用') && s.status !== 'RETIRED') {
                    await fetch('/api/v1/workload/standards/' + s.id + '/retire', {
                      method: 'POST', headers: h,
                    });
                    out.push('standard:' + s.code);
                  }
                }
                const pilotPaths = await fetch('/api/v1/pilot/paths', { headers: h }).then(r => r.json());
                for (const p of pilotPaths) {
                  if (p.name.includes('自检用')) {
                    await fetch('/api/v1/pilot/paths/' + p.id, { method: 'DELETE', headers: h });
                    out.push('pilot-path:' + p.name);
                  }
                }
                return out;
              }
            """
            removed = page.evaluate(script, skipped_keys)
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
