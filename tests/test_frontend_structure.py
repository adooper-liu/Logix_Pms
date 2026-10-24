"""前端模块结构的静态守卫。

前端是原生 ES 模块、没有构建步骤，所以「import 路径写错」不会在编译期报错，
只会在浏览器里静默 404。这组用例把这类问题提前到测试阶段。
"""

from __future__ import annotations

import re
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent.parent / "web"
JS_ROOT = WEB_ROOT / "js"

IMPORT_RE = re.compile(r"""from\s+['"]([^'"]+)['"]""")


def _modules() -> list[Path]:
    return sorted(JS_ROOT.rglob("*.js"))


def test_frontend_has_modules():
    names = {p.name for p in _modules()}
    # 核心层
    assert {
        "api.js",
        "auth.js",
        "format.js",
        "metrics.js",
        "router.js",
        "state.js",
        "theme.js",
        "ui.js",
        "actions.js",
    } <= names
    # 各业务视图
    assert {
        "dashboard.js",
        "strategy.js",
        "map.js",
        "pcf.js",
        "workflow.js",
        "projects.js",
        "toolbox.js",
        "designer.js",
        "monitor.js",
        "knowledge.js",
        "execution.js",
        "deliverables.js",
        "orgs.js",
        "sketches.js",
    } <= names
    assert "main.js" in names

    # designer 拆包的目标结构（少一个就说明拆分没落地或被误删）
    designer_modules = {p.name for p in (JS_ROOT / "views" / "designer").glob("*.js")}
    assert {
        "index.js",
        "canvas.js",
        "providers.js",
        "xml.js",
        "panels.js",
        "assignment.js",
        "lint.js",
        "versions.js",
        "transfer.js",
        "changes.js",
    } <= designer_modules


def test_all_relative_imports_resolve():
    """每个 `from './x.js'` 都必须指向真实存在的文件。"""
    broken = []
    for module in _modules():
        for target in IMPORT_RE.findall(module.read_text(encoding="utf-8")):
            if not target.startswith("."):
                continue  # 不处理裸模块名（本项目没有）
            resolved = (module.parent / target).resolve()
            if not resolved.exists():
                broken.append(f"{module.name} -> {target}")
    assert not broken, "存在无效的 import 路径：\n" + "\n".join(broken)


NAMED_IMPORT_RE = re.compile(r"import\s*\{([^}]*)\}\s*from\s*['\"]([^'\"]+)['\"]", re.S)
EXPORT_DECL_RE = re.compile(
    r"export\s+(?:async\s+)?(?:function|const|let|var|class)\s+([A-Za-z_$][\w$]*)"
)
EXPORT_LIST_RE = re.compile(r"export\s*\{([^}]*)\}", re.S)


def _exported_names(src: str) -> set[str]:
    names = set(EXPORT_DECL_RE.findall(src))
    for group in EXPORT_LIST_RE.findall(src):
        for item in group.split(","):
            item = item.strip()
            if not item:
                continue
            # `a as b` 对外暴露的是别名 b
            names.add(item.split(" as ")[-1].strip())
    return names


def test_named_imports_exist_in_target_module():
    """import 的具名符号必须在目标模块里真的 export。

    回归背景：拆 `designer/xml.js` 时函数被吞进未闭合的块注释、模块没有任何
    export，但旧守卫只检查源码里出现 `function xxx(`，测试全绿而浏览器加载即报
    「does not provide an export named」。
    """
    missing = []
    for module in _modules():
        src = module.read_text(encoding="utf-8")
        for names, target in NAMED_IMPORT_RE.findall(src):
            if not target.startswith("."):
                continue
            resolved = (module.parent / target).resolve()
            if not resolved.exists():
                continue  # 路径问题由上一个用例负责
            exported = _exported_names(resolved.read_text(encoding="utf-8"))
            for spec in names.split(","):
                spec = spec.strip()
                if not spec:
                    continue
                name = spec.split(" as ")[0].strip()
                if name not in exported:
                    rel = module.relative_to(JS_ROOT).as_posix()
                    missing.append(f"{rel}: {name} 不在 {target} 的导出中")
    assert not missing, "存在无法解析的具名 import：\n" + "\n".join(missing)


def test_view_modules_are_registered():
    """main.js 必须注册全部业务视图，否则对应页面会是空白。"""
    main_src = (JS_ROOT / "main.js").read_text(encoding="utf-8")
    for view in (
        "dashboard",
        "strategy",
        "map",
        "pcf",
        "workflow",
        "projects",
        "toolbox",
        "designer",
        "monitor",
        "knowledge",
        "execution",
        "deliverables",
        "orgs",
        "sketches",
    ):
        assert f"register('{view}'" in main_src, f"main.js 没有注册视图 {view}"


def test_knowledge_view_wires_pagination():
    """知识库标题写「N 条」，就必须把 page 传下去并提供翻页入口。

    回归背景：page_size 固定 50 且不传 page，第 51 条以后永远看不到。
    """
    src = (JS_ROOT / "views" / "knowledge.js").read_text(encoding="utf-8")
    assert "'page=' +" in src, "knowledge.js 没有把 page 传给后端"
    assert "setKPage" in src, "knowledge.js 没有翻页动作"
    assert "上一页" in src and "下一页" in src, "knowledge.js 没有渲染翻页按钮"


def test_actions_registry_is_a_leaf():
    """actions.js 不能 import 视图，否则视图↔注册表会成环。"""
    src = (JS_ROOT / "core" / "actions.js").read_text(encoding="utf-8")
    assert "registerActions" in src and "actionKeys" in src
    assert not re.search(r"from\s+['\"]\.\./views/", src), "actions.js 不得 import 视图"
    assert not re.search(r"from\s+['\"]\./views/", src), "actions.js 不得 import 视图"


def test_ui_delegation_covers_multiple_event_types():
    """只监听 click 会漏掉筛选器的 change/input 和表单 submit。"""
    src = (JS_ROOT / "core" / "ui.js").read_text(encoding="utf-8")
    for event in ("click", "change", "input", "submit", "keydown"):
        assert f"'{event}'" in src, f"委托根缺少 {event} 事件"
    assert "data-act" in src and "export function on(" in src
    assert "confirmDialog" in src and "promptDialog" in src


def test_data_act_is_only_on_interactive_elements():
    """data-act 不允许挂在 div/span 上，否则键盘不可用。"""
    bad = []
    for module in _modules():
        src = module.read_text(encoding="utf-8")
        for match in re.finditer(r"<(div|span)\b[^>]*\bdata-act=", src):
            bad.append(f"{module.name}: {match.group(0)[:80]}")
    assert not bad, "data-act 只能挂在 button/a 上：\n" + "\n".join(bad)


def test_data_act_keys_are_namespaced():
    keys = set()
    for module in (JS_ROOT / "views").rglob("*.js"):
        src = module.read_text(encoding="utf-8")
        keys |= set(re.findall(r'data-act="([^"]+)"', src))
    pattern = re.compile(r"^[a-z][a-z0-9]*\.[A-Za-z][A-Za-z0-9_]*$")
    invalid = sorted(key for key in keys if not pattern.match(key))
    assert not invalid, f"data-act 键必须带视图前缀：{invalid}"


def test_native_dialogs_do_not_grow():
    """Phase 1A 不改存量视图；用基线数量防止新代码继续引入原生弹窗。"""
    hits = []
    for module in (JS_ROOT / "views").rglob("*.js"):
        src = module.read_text(encoding="utf-8")
        hits.extend(re.findall(r"\b(confirm|prompt|alert)\(", src))
    assert len(hits) == 0, f"视图内仍有原生 confirm/prompt/alert：{len(hits)} 处"


INLINE_HANDLER_RE = re.compile(
    r"\bon(click|change|input|submit|keydown|keyup|blur|focus|toggle)\s*=\s*[\"']"
)


def test_no_inline_event_handlers():
    """行为必须写在 JS 里；模板只允许 data-act。"""
    bad = []
    modules = list(JS_ROOT.rglob("*.js")) + [WEB_ROOT / "index.html"]
    for module in modules:
        for line_no, line in enumerate(module.read_text(encoding="utf-8").splitlines(), 1):
            if INLINE_HANDLER_RE.search(line):
                bad.append(f"{module.relative_to(WEB_ROOT)}:{line_no}")
    assert not bad, "仍有内联事件处理器：\n" + "\n".join(bad)


def test_views_do_not_import_other_views():
    """视图之间只允许 import views/shared/ 或 core/，不允许直接 import 另一个视图。"""
    bad = []
    for module in sorted((JS_ROOT / "views").glob("*.js")):
        src = module.read_text(encoding="utf-8")
        for target in re.findall(r"from\s+['\"]\./([^'\"]+)['\"]", src):
            if target.startswith("shared/") or "/" in target:
                continue
            if target.endswith(".js"):
                bad.append(f"{module.name} -> {target}")
    assert not bad, "视图之间仍有直接 import：\n" + "\n".join(bad)


def test_view_action_keys_are_namespaced_and_unique():
    action_re = re.compile(r"export\s+const\s+actions\s*=\s*\{(.*?)\};", re.S)
    key_re = re.compile(r"['\"]([^'\"]+)['\"]\s*:")
    owners: dict[str, str] = {}
    name_re = re.compile(r"^[a-z][a-z0-9]*\.[A-Za-z][A-Za-z0-9_]*$")
    for module in sorted((JS_ROOT / "views").glob("*.js")):
        match = action_re.search(module.read_text(encoding="utf-8"))
        if not match:
            continue
        for key in key_re.findall(match.group(1)):
            assert name_re.match(key), f"{module.name} 的 action 未带视图前缀：{key}"
            assert key not in owners, f"action 重名：{key}（{owners[key]} / {module.name}）"
            owners[key] = module.name


def test_window_surface_is_minimal():
    src = (JS_ROOT / "main.js").read_text(encoding="utf-8")
    match = re.search(r"Object\.assign\(window,\s*\{([^}]*)\}", src)
    assert match, "main.js 缺少 window 操作面声明"
    surface = match.group(1)
    names = {part.strip() for part in surface.split(",") if part.strip()}
    assert names == {"go", "closeModal", "state", "actions"}, (
        f"window 对外操作面应收窄为 go / closeModal / state / actions，当前：{sorted(names)}"
    )
    assert "registerActions(" in src, "main.js 没有注册视图 actions"


def test_core_does_not_import_views():
    bad = []
    for module in sorted((JS_ROOT / "core").rglob("*.js")):
        src = module.read_text(encoding="utf-8")
        if re.search(r"from\s+['\"]\.\./views/", src):
            bad.append(module.name)
    assert not bad, f"core 反向 import 视图：{bad}"


def test_js_block_comments_are_balanced():
    """块注释必须闭合，且不允许出现游离的 `* ... */` 行。

    回归背景：拆 `designer.js` 时把注释开头搬进了 `designer/xml.js`、结尾留在原地，
    浏览器报 `Unexpected token '*'`；这种错误 Python 测试若不扫源码就完全看不见。
    """
    bad = []
    for module in _modules():
        in_block = False
        for line_no, line in enumerate(module.read_text(encoding="utf-8").splitlines(), 1):
            if not in_block and re.match(r"^\s*\*", line):
                bad.append(f"{module.relative_to(JS_ROOT)}:{line_no} 游离的注释行")
            cursor = 0
            while cursor < len(line):
                if in_block:
                    end = line.find("*/", cursor)
                    if end < 0:
                        break
                    in_block = False
                    cursor = end + 2
                else:
                    start = line.find("/*", cursor)
                    if start < 0:
                        break
                    in_block = True
                    cursor = start + 2
        if in_block:
            bad.append(f"{module.relative_to(JS_ROOT)} 文件结束时仍有未闭合的块注释")
    assert not bad, "JS 注释结构异常：\n" + "\n".join(bad)


def test_designer_xml_module_is_pure():
    """BPMN XML 手术必须保持纯函数，方便单测与复用。"""
    xml_src = (JS_ROOT / "views" / "designer" / "xml.js").read_text(encoding="utf-8")
    for forbidden in ("fetch(", "state.", "toast(", "document.", "openModal(", "closeModal("):
        assert forbidden not in xml_src, f"designer/xml.js 不应依赖 {forbidden}"
    for symbol in ("appendBpmnLane", "restoreLanes", "ensureFlowRefs", "orthogonalizePath"):
        assert f"function {symbol}(" in xml_src, f"designer/xml.js 缺少 {symbol}"


def test_designer_shell_is_thin_and_wires_submodules():
    """designer.js 只做薄壳；实现全部在 ./designer/ 里，且由 index 统一组装。"""
    shell = (JS_ROOT / "views" / "designer.js").read_text(encoding="utf-8")
    assert "from './designer/index.js'" in shell, "designer.js 没有委托给 designer/index.js"
    assert "function paintDesigner(" not in shell, "designer.js 仍有页面渲染逻辑"

    index_src = (JS_ROOT / "views" / "designer" / "index.js").read_text(encoding="utf-8")
    assert "export function renderDesigner(" in index_src
    assert "export const actions" in index_src
    for factory in (
        "createCanvas",
        "createPanels",
        "createAssignment",
        "createLint",
        "createVersions",
        "createTransfer",
        "createChanges",
    ):
        assert f"{factory}(ctx)" in index_src, f"index.js 没有组装 {factory}"
    for hook in (
        "renderSelection",
        "runLint",
        "renderBpmnAssignment",
        "hydrateBpmnNodeExtras",
        "saveNow",
        "closeSidebar",
    ):
        assert hook in index_src, f"ctx 没有注入 {hook}"


def test_designer_module_sizes_are_bounded():
    """拆分不是把一个大文件摊成九个，单个模块必须有内聚上限。"""
    subdir = JS_ROOT / "views" / "designer"
    oversized = []
    for module in sorted(subdir.glob("*.js")):
        lines = len(module.read_text(encoding="utf-8").splitlines())
        if lines > 700:
            oversized.append(f"{module.name}: {lines} 行")
    assert not oversized, "designer 子模块超过 700 行，应继续按职责拆分：\n" + "\n".join(oversized)

    shell_lines = len((JS_ROOT / "views" / "designer.js").read_text(encoding="utf-8").splitlines())
    assert shell_lines <= 30, f"designer.js 应保持薄壳，当前 {shell_lines} 行"


def test_designer_submodules_do_not_import_each_other():
    """子模块只通过 ctx 协作；互相 import 会重新长成一张网。

    xml.js（纯函数）和 providers.js（bpmn-js 扩展点）不持有状态，可以共享；
    其余模块一律不得互相 import。
    """
    subdir = JS_ROOT / "views" / "designer"
    forbidden = {
        "canvas.js",
        "panels.js",
        "assignment.js",
        "lint.js",
        "versions.js",
        "transfer.js",
        "changes.js",
        "index.js",
    }
    bad = []
    for module in sorted(subdir.glob("*.js")):
        if module.name == "index.js":
            continue
        for target in IMPORT_RE.findall(module.read_text(encoding="utf-8")):
            if target.startswith(".") and Path(target).name in forbidden:
                bad.append(f"{module.name} -> {target}")
    assert not bad, "designer 子模块不得互相 import：\n" + "\n".join(bad)


def test_view_exports_do_not_collide():
    """视图导出的函数会被 Object.assign(window, ...) 合并；重名会静默覆盖。

    真实事故：pcf.js 和 map.js 都导出 togglePcfNode，后者覆盖前者，
    向导里的 checkbox 因此点了没反应。这里提前拦住同类问题。
    """
    owners: dict[str, str] = {}
    export_re = re.compile(r"export\s*\{([^}]*)\}", re.S)
    for module in sorted((JS_ROOT / "views").glob("*.js")):
        for match in export_re.finditer(module.read_text(encoding="utf-8")):
            for raw in match.group(1).split(","):
                name = raw.strip().split(" as ")[-1].strip()
                if not name:
                    continue
                assert name not in owners, (
                    f"{name} 同时由 {owners[name]} 和 {module.name} 导出；"
                    "main.js 会把它们挂到 window，后者会覆盖前者"
                )
                owners[name] = module.name


def test_every_view_module_exports_a_renderer():
    renderers = {
        "dashboard.js": "renderDashboard",
        "strategy.js": "renderStrategy",
        "map.js": "renderMap",
        "pcf.js": "renderPcf",
        "workflow.js": "renderWorkflow",
        "projects.js": "renderProjects",
        "toolbox.js": "renderToolbox",
        "designer.js": "renderDesigner",
        "monitor.js": "renderMonitor",
        "knowledge.js": "renderKnowledge",
        "execution.js": "renderExecution",
        "deliverables.js": "renderDeliverables",
        "orgs.js": "renderOrgs",
        "sketches.js": "renderSketches",
    }
    for filename, symbol in renderers.items():
        src = (JS_ROOT / "views" / filename).read_text(encoding="utf-8")
        if filename == "designer.js":
            # designer 是薄壳，实现与导出都在 ./designer/index.js
            assert "from './designer/index.js'" in src, "designer.js 没有委托给子模块"
            index_src = (JS_ROOT / "views" / "designer" / "index.js").read_text(encoding="utf-8")
            assert re.search(r"\bexport function renderDesigner\b", index_src), (
                "designer/index.js 没有导出 renderDesigner"
            )
            continue
        assert re.search(rf"\bconst {symbol}\b", src), f"{filename} 缺少 {symbol}"
        assert re.search(rf"export \{{[^}}]*\b{symbol}\b", src), f"{filename} 没有导出 {symbol}"


def test_stylesheets_exist_and_are_referenced():
    html = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    for name in ("base.css", "components.css", "views.css"):
        assert (WEB_ROOT / "css" / name).exists(), f"缺少 {name}"
        assert f"/static/css/{name}" in html, f"index.html 没有引用 {name}"
    # 不能再引用拆分前的旧文件
    assert "/static/styles.css" not in html
    assert "/static/app.js" not in html
    assert "/static/views.js" not in html


def test_metric_help_keys_are_registered():
    """视图里引用的指标口径 key 必须在 core/metrics.js 注册，否则提示会静默消失。"""
    metrics_src = (JS_ROOT / "core" / "metrics.js").read_text(encoding="utf-8")
    registered = set(re.findall(r"^  ([a-z_]+):\s*\{", metrics_src, re.MULTILINE))
    used: set[str] = set()
    for module in (JS_ROOT / "views").rglob("*.js"):
        used |= set(re.findall(r"metricHelp\('([a-z_]+)'", module.read_text(encoding="utf-8")))
    missing = sorted(used - registered)
    assert not missing, f"以下指标未在 metrics.js 注册：{missing}"


def test_components_have_no_hardcoded_colors():
    """颜色只能出现在主题令牌层；组件和视图一律用 var(--token)。"""
    hex_re = re.compile(r"#[0-9a-fA-F]{3,8}\b")
    for name in ("components.css", "views.css"):
        src = (WEB_ROOT / "css" / name).read_text(encoding="utf-8")
        colors = hex_re.findall(src)
        assert not colors, f"{name} 仍存在硬编码颜色：{sorted(set(colors))[:8]}"

    base = (WEB_ROOT / "css" / "base.css").read_text(encoding="utf-8")
    assert '[data-theme="slate"]' in base, "base.css 缺少主题覆盖示例"
    assert "--brand:" in base and "--panel:" in base, "base.css 缺少基础主题令牌"
