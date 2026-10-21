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
    assert {"api.js", "auth.js", "format.js", "router.js", "state.js", "ui.js"} <= names
    # 八个视图
    assert {
        "dashboard.js",
        "map.js",
        "workflow.js",
        "projects.js",
        "toolbox.js",
        "designer.js",
        "monitor.js",
        "knowledge.js",
    } <= names
    assert "main.js" in names


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


def test_view_modules_are_registered():
    """main.js 必须注册全部八个视图，否则对应页面会是空白。"""
    main_src = (JS_ROOT / "main.js").read_text(encoding="utf-8")
    for view in (
        "dashboard",
        "map",
        "workflow",
        "projects",
        "toolbox",
        "designer",
        "monitor",
        "knowledge",
    ):
        assert f"register('{view}'" in main_src, f"main.js 没有注册视图 {view}"


def test_every_view_module_exports_a_renderer():
    renderers = {
        "dashboard.js": "renderDashboard",
        "map.js": "renderMap",
        "workflow.js": "renderWorkflow",
        "projects.js": "renderProjects",
        "toolbox.js": "renderToolbox",
        "designer.js": "renderDesigner",
        "monitor.js": "renderMonitor",
        "knowledge.js": "renderKnowledge",
    }
    for filename, symbol in renderers.items():
        src = (JS_ROOT / "views" / filename).read_text(encoding="utf-8")
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
