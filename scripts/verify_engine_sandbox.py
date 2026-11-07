"""Exercise the current PMS/Runner sandbox using real APIs and original pages only."""

import json
import sys
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8124"
if BASE != "http://127.0.0.1:8124":
    raise SystemExit("Explicit isolated PMS sandbox 8124 required")
OPENER = build_opener(ProxyHandler({}))


def call(path, body=None, token=None, method=None):
    headers = {"Content-Type": "application/json", "Idempotency-Key": str(uuid.uuid4())}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = Request(
        BASE + "/api/v1" + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
        method=method or ("POST" if body is not None else "GET"),
    )
    try:
        with OPENER.open(request, timeout=30) as response:
            value = json.load(response)
            if isinstance(value, dict) and value.get("command_id") and value.get("error"):
                raise AssertionError(value)
            return value
    except HTTPError as error:
        raise AssertionError((path, error.code, error.read().decode())) from None


def main():
    admin = call("/auth/login", {"username": "admin", "password": "admin123"})["token"]
    manager = call("/auth/login", {"username": "manager", "password": "manager123"})["token"]
    who = call("/auth/me", token=admin)
    reviewer = call("/auth/me", token=manager)
    from tests.test_engine_bpmn import PARALLEL, SERIAL

    serial = "--serial" in sys.argv
    xml = SERIAL if serial else PARALLEL
    task_keys = ["a"] if serial else ["a", "b"]

    pid = call(
        "/process-map",
        {"code": "R3-E2E-" + uuid.uuid4().hex[:6], "name": "沙箱并行办理验收", "level": 3},
        admin,
    )["id"]
    model = call(f"/processes/{pid}/bpmn", {"xml": xml, "execution_provider": "FLOWABLE"}, admin)
    call(f"/processes/{pid}/design/submit-review", {}, admin)
    model = call(
        f"/processes/{pid}/design/publish",
        {"change_note": "合成沙箱发布验证", "expected_version": model["version"]},
        manager,
    )
    for key in task_keys:
        call(
            "/execution/assignments",
            {"process_id": pid, "node_key": key, "default_assignee_user_id": who["id"]},
            admin,
            "PUT",
        )
    ready = call(f"/execution/readiness?process_id={pid}", token=admin)
    ready = call(
        f"/execution/readiness?process_id={pid}",
        {
            "expected_revision": ready["revision"],
            "reviewer_user_id": reviewer["id"],
            "requirements": {
                key: {"mode": "NOT_APPLICABLE", "reason": "仅合成沙箱，非业务上线"}
                for key in ["forms", "assignments", "deadlines"]
            },
            "evidence": "使用固定合成模型核对正常与并行汇聚",
            "rollback_note": "关闭沙箱新启动，保留在途核对",
        },
        admin,
        "PUT",
    )
    ready = call(
        f"/execution/readiness/confirm?process_id={pid}",
        {
            "expected_revision": ready["revision"],
            "decision": "ACCEPT",
            "evidence": "本人核对合成沙箱与原配置",
        },
        manager,
    )
    assert ready["confirmed"], ready
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.goto(BASE)
        page.fill("#loginUser", "admin")
        page.fill("#loginPass", "admin123")
        page.click("#loginBtn")
        page.wait_for_function("!document.getElementById('loginMask').offsetParent")
        page.wait_for_timeout(1000)
        page.goto(BASE + f"/#execution?tab=config&process={pid}")
        page.wait_for_timeout(1500)
        if page.locator('[data-act="engine.deploy"]').count() == 0:
            page.locator('a[data-view="execution"]').click()
            page.wait_for_timeout(500)
            page.locator('[data-act="execution.tab"][data-tab="config"]').click()
            page.wait_for_timeout(800)
            page.select_option("#exConfigProcess", str(pid))
            page.wait_for_timeout(800)
        page.locator('[data-act="engine.deploy"]').click()
        page.wait_for_timeout(1200)
        page.locator('[data-act="engine.enable"]').click()
        page.wait_for_timeout(1000)
        status = call(f"/execution/engine/status?process_id={pid}", token=admin)
        assert status["allow_start"], status
        # Start through the original execution modal, not a new engine console.
        page.locator('[data-act="execution.startModal"]').first.click()
        page.wait_for_timeout(500)
        page.select_option("#exProcess", str(pid))
        page.wait_for_timeout(500)
        page.locator('[data-act="execution.submitStart"]').click()
        page.wait_for_timeout(1000)
        page.goto(BASE + "/#execution?tab=tasks")
        page.wait_for_timeout(1200)
        instances = call(f"/execution/instances?process_id={pid}", token=admin)
        assert len(instances) == 1, instances
        ident = instances[0]["id"]
        detail = call(f"/execution/instances/{ident}", token=admin)
        assert len(detail["active_tasks"]) == len(task_keys)
        page.locator('[data-act="execution.filter"][data-filter="queue"]').click()
        page.wait_for_timeout(500)
        for index, task in enumerate(detail["active_tasks"]):
            page.locator(f'[data-act="execution.openTask"][data-id="{task["id"]}"]').first.click()
            page.wait_for_timeout(600)
            page.locator('[data-act="execution.completeTask"]').click()
            page.wait_for_timeout(800)
            progress = call(f"/execution/instances/{ident}", token=admin)
            assert progress["instance"]["status"] == (
                "COMPLETED" if index == len(task_keys) - 1 else "RUNNING"
            )
        done = call(f"/execution/instances/{ident}", token=admin)
        assert done["instance"]["status"] == "COMPLETED", done
        page.goto(BASE + f"/#execution?tab=instances&process={pid}")
        page.wait_for_timeout(800)
        Path("var/r3-sandbox").mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path="var/r3-sandbox/" + ("serial-e2e.png" if serial else "parallel-e2e.png"),
            full_page=True,
        )
        browser.close()
    print(
        "PASS published exact XML / distinct reviewer / deployed / enabled / original UI "
        + ("serial" if serial else "parallel join"),
        pid,
        ident,
    )
    Path("var/r3-sandbox/e2e-result.json").write_text(
        json.dumps(
            {"process_id": pid, "instance_id": ident, "model_version_id": model["version_id"]}
        )
    )


if __name__ == "__main__":
    main()
