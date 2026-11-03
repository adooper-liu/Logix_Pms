"""工具模板保存回归：真实界面不自动申报效果，独立入口只使用临时库。"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen
from uuid import uuid4

from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SHEET_SOURCE = "web/js/views/shared/tool_sheet.js"


def verify_tool_sheet_save(page: Page, base: str) -> None:
    """消费已登录页面；成功路径访问真实API，只有400负例拦截一次请求。"""
    token = page.evaluate("localStorage.getItem('psm_token')")
    assert token, "工具保存回归需要已登录页面"
    headers = {"Authorization": "Bearer " + token}
    requests: list[str] = []
    objectives: list[int] = []
    project_id = None
    marker = "sheet-check-" + uuid4().hex[:10]

    def api(method, path, data=None):
        response = page.request.fetch(
            base.rstrip("/") + "/api/v1" + path, method=method, headers=headers, data=data
        )
        assert response.ok, f"验证API失败：{method} {path} ({response.status})"
        return response.json()

    def usage_ids(code):
        rows = api("GET", f"/tools/{code}/usage?limit=200")
        assert len(rows) < 200, "验证库使用事件达到分页上限，不能据截断列表判断未新增"
        return {row["id"] for row in rows}

    def observe(request):
        if request.method == "POST":
            requests.append(urlsplit(request.url).path)

    def open_sheet(code, step="", project=False):
        page.evaluate("() => closeModal()")
        if project:
            page.evaluate(
                "id => go('projects', {params:{project:String(id)}, skipOrigin:true})",
                project_id,
            )
            page.wait_for_load_state("networkidle")
            page.evaluate("() => closeModal()")
        # 空step会被URL规范化省略；普通场景显式清理步骤筛选，
        # 防止复用已登录页面时继承上一场景的界面态。
        if not step:
            page.evaluate("() => { state.toolbox.step = ''; state.toolboxFilter = null; }")
        page.evaluate(
            "params => go('toolbox', {params, skipOrigin: !params.step})",
            {"open": code, "process": str(process_id), "step": step},
        )
        page.wait_for_load_state("networkidle")
        expect(page.locator("#view .tb-detail-card")).to_be_visible()
        if project:
            assert page.evaluate(
                "id => state.navTrail.some(row => Number(row.params.project) === id)",
                project_id,
            ), "来源栈丢失项目上下文"
        button = page.locator(f'#view [data-act="toolbox.fillSheet"][data-code="{code}"]').first
        button.click()
        expect(page.locator("#tsProcess")).to_be_visible()
        form = api("GET", f"/tools/{code}/sheet-form")
        values = {}
        for field in form["fields"]:
            value = {"baseline": "14", "target": "5", "unit": "天"}.get(
                field["key"], marker + "-" + field["key"]
            )
            element = page.locator("#ts-" + field["key"])
            if field["kind"] == "choice" and field["options"]:
                value = field["options"][0]
                element.select_option(value)
            else:
                element.fill(value)
            values[field["key"]] = value
        page.select_option("#tsProcess", str(process_id))
        return values

    page.on("request", observe)
    try:
        processes = api("GET", "/process-map/flat")
        process_id = next(row["id"] for row in processes if row["code"] == "L3-032")
        created = api(
            "POST",
            "/projects",
            {
                "name": "自检用-tool-sheet-" + marker,
                "methodology": "BPI",
                "owner": "流程管理科",
                "process_id": process_id,
            },
        )
        project_id = created["id"]
        for code, step, project in [
            ("SIPOC", "", False),
            ("SIPOC", "2.1", True),
            ("OGSM", "1.2", True),
        ]:
            before = usage_ids(code)
            values = open_sheet(code, step, project)
            requests.clear()
            with page.expect_response(
                lambda response, code=code: (
                    response.request.method == "POST"
                    and urlsplit(response.url).path == f"/api/v1/tools/{code}/sheets"
                )
            ) as saved_response:
                page.locator('#mFoot [data-act="toolbox.submitSheet"]').click()
            response = saved_response.value
            assert response.status == 201, response.text()
            saved = response.json()
            if saved.get("objective_id"):
                objectives.append(saved["objective_id"])
            expect(page.locator("#mask")).not_to_have_class("mask show")
            page.wait_for_load_state("networkidle")
            assert requests.count(f"/api/v1/tools/{code}/sheets") == 1
            count = requests.count(f"/api/v1/tools/{code}/usage")
            assert count == 0, f"保存不得POST usage，实际{count}次 ({code}, step={step})"
            assert usage_ids(code) == before, "保存模板增加了效果申报记录"
            assert saved["process_id"] == process_id
            assert saved["project_id"] == (project_id if project else None)
            assert saved["step_no"] == (step or None)
            assert {row["key"]: row["value"] for row in saved["fields"]} == values
            card = api("GET", f"/process-card/{process_id}")
            assert any(row["id"] == saved["id"] for row in card["sheets"])
            if code == "OGSM":
                assert saved["objective_codes"], "OGSM目标生成被误删"
                objective = api("GET", f"/strategy/objectives/{saved['objective_id']}")
                assert objective["name"] == values["direction"]
            print(f"OK   模板保存不自动申报效果：{code}, step={step or 'none'}")

        before = usage_ids("SIPOC")
        values = open_sheet("SIPOC", "2.1", True)
        requests.clear()
        endpoint = "**/api/v1/tools/SIPOC/sheets"

        def reject(route):
            route.fulfill(status=400, json={"detail": "测试校验失败"})

        page.route(endpoint, reject)
        try:
            page.locator('#mFoot [data-act="toolbox.submitSheet"]').click()
            expect(page.locator("#toast")).to_contain_text("测试校验失败")
            expect(page.locator("#tsProcess")).to_be_visible()
            for key, value in values.items():
                expect(page.locator("#ts-" + key)).to_have_value(value)
            assert "/api/v1/tools/SIPOC/usage" not in requests
            assert usage_ids("SIPOC") == before
        finally:
            page.unroute(endpoint, reject)
            page.evaluate("() => closeModal()")
        print("OK   保存失败保留输入且无效果申报")

        # 当前页面未渲染显式工具申报按钮；用原API核对用户主动提交契约，
        # 不为测试新增业务按钮，也不将API对照冒称为UI入口验收。
        explicit_step = uuid4().hex[:8]
        event = api(
            "POST",
            "/tools/SIPOC/usage",
            {
                "project_id": project_id,
                "step_no": explicit_step,
                "outcome": "PARTIAL",
                "note": marker + "-explicit",
            },
        )
        assert event["outcome"] == "PARTIAL" and event["step_no"] == explicit_step
        assert event["project_id"] == project_id
        assert event["note"] == marker + "-explicit"
        assert usage_ids("SIPOC") - before == {event["id"]}
        print("OK   显式效果申报API保留（当前无可见工具申报按钮，非UI验收）")
    finally:
        page.remove_listener("request", observe)
        page.evaluate("() => closeModal()")
        for objective_id in objectives:
            api("DELETE", f"/strategy/objectives/{objective_id}")
        if project_id is not None:
            api("DELETE", f"/projects/{project_id}")
        page.evaluate("() => go('start', {skipOrigin:true})")
        page.wait_for_load_state("networkidle")


@contextmanager
def isolated_app():
    """只启动并清理本次子进程；调用者不能提供外部数据库或服务地址。"""
    with tempfile.TemporaryDirectory(
        prefix="logix-sheet-", ignore_cleanup_errors=True
    ) as directory:
        folder = Path(directory)
        database_url = "sqlite:///" + (folder / "app.db").as_posix()
        env = os.environ.copy()
        env.update(
            DATABASE_URL=database_url,
            TEST_DATABASE_URL="",
            ALLOW_DEV_SECRET="true",
            SEED_ON_STARTUP="true",
            AUTO_MIGRATE="true",
            ATTACHMENT_BACKEND="local",
            ATTACHMENT_DIR=str(folder / "attachments"),
            PREVIEW_CONVERTER="none",
            PYTHONUTF8="1",
        )
        subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.core.config import settings; import os; assert settings.is_sqlite and settings.database_url == os.environ['DATABASE_URL']; print('Isolated SQLite settings: OK')",
            ],
            cwd=ROOT,
            env=env,
            check=True,
        )
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with (folder / "server.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "app.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(120):
                    if process.poll() is not None:
                        raise RuntimeError(
                            "隔离服务启动失败："
                            + (folder / "server.log").read_text(encoding="utf-8")[-4000:]
                        )
                    try:
                        with urlopen(base + "/health", timeout=1) as response:
                            health = json.load(response)
                        if health.get("database") == "sqlite" and health.get("database_ok"):
                            break
                    except (URLError, TimeoutError):
                        pass
                    time.sleep(0.25)
                else:
                    raise RuntimeError("隔离服务未就绪")
                with urlopen(base + "/static/js/views/shared/tool_sheet.js", timeout=5) as response:
                    served = response.read()
                assert (
                    hashlib.sha256(served).digest()
                    == hashlib.sha256((ROOT / SHEET_SOURCE).read_bytes()).digest()
                ), "服务静态文件不是当前代码"
                yield base, folder
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    with isolated_app() as (base, _folder), sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page()
            page.goto(base, wait_until="networkidle")
            page.fill("#loginUser", "admin")
            page.fill("#loginPass", "admin123")
            page.click("#loginBtn")
            expect(page.locator("#loginMask")).not_to_be_visible()
            page.wait_for_load_state("networkidle")
            verify_tool_sheet_save(page, base)
        finally:
            browser.close()
    print("工具模板保存回归：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
