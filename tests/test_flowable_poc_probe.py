"""POC probe must fail closed and retain operation identity on transport failure."""

import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_flowable_poc.py"


@pytest.fixture(autouse=True)
def isolated_command_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)


def load():
    spec = importlib.util.spec_from_file_location("flowable_probe", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com",
        "http://127.0.0.1:8123",
        "http://user:pass@localhost:8135",
        "https://localhost:8135",
        "http://localhost:8135/path",
        "http://127.0.0.1:8135?x=1",
    ],
)
def test_reject_non_loopback_or_wrong_target(url):
    with pytest.raises(ValueError):
        load().Client(url, "x" * 32, "sha")


def test_redirect_is_not_followed():
    handler = load().NoRedirect()
    assert handler.redirect_request(None, None, 302, "redirect", {}, "http://example.com") is None


@pytest.mark.parametrize(
    "info", [{"poc": False, "build_revision": "sha"}, {"poc": True, "build_revision": "old"}]
)
def test_reject_revision_or_poc_marker_mismatch(info):
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")
    client.get = lambda path: info
    with pytest.raises(ValueError):
        client.check_identity()


def test_drain_all_event_pages_and_deduplicate():
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")
    pages = iter(
        [
            {"events": [{"event_id": "a", "journal_id": 1}], "next_after_id": 1, "has_more": True},
            {"events": [{"event_id": "b", "journal_id": 2}], "next_after_id": 2, "has_more": False},
        ]
    )
    paths = []

    def get(path):
        paths.append(path)
        return next(pages)

    client.get = get
    seen, cursor = client.events(0, {"a"})
    assert [e["event_id"] for e in seen] == ["b"]
    assert cursor == 2
    assert "after_id=1" in paths[1]


def test_deadline_expires_with_last_state():
    with pytest.raises(TimeoutError, match="RUNNING"):
        load().wait_for(
            lambda: {"status": "RUNNING"}, lambda x: x["status"] == "COMPLETED", timeout=0.01
        )


def test_reuse_original_command_after_timeout():
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")
    sent = []

    def post(path, payload):
        sent.append(payload)
        raise URLError("timeout")

    client.post = post
    client.get = lambda path: {
        "command_id": sent[0]["command_id"],
        "result": {"instance_id": "original"},
    }
    result = client.command("START", "definition", {"business_key": "poc:test"})
    assert result["instance_id"] == "original"
    assert len(sent) == 1


def test_missing_command_after_timeout_retries_same_id():
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")
    sent = []

    def post(path, payload):
        sent.append(payload.copy())
        if len(sent) == 1:
            raise URLError("timeout")
        return {"command_id": payload["command_id"], "result": {"instance_id": "original"}}

    def get(path):
        raise HTTPError(path, 404, "not committed", {}, None)

    client.post = post
    client.get = get
    assert client.command("START", "definition", {})["instance_id"] == "original"
    assert sent[0] == sent[1]


def test_proxy_environment_cannot_route_loopback_token(monkeypatch, tmp_path):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    routed = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routed.append((self.server.server_port, self.headers.get("Authorization")))
            body = b'{"poc":true,"build_revision":"sha"}'
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    servers = [ThreadingHTTPServer(("127.0.0.1", 0), Handler) for _ in range(2)]
    threads = [Thread(target=s.serve_forever, daemon=True) for s in servers]
    for thread in threads:
        thread.start()
    try:
        direct, proxy = servers
        proxy_url = f"http://127.0.0.1:{proxy.server_port}"
        monkeypatch.setenv("http_proxy", proxy_url)
        monkeypatch.setenv("HTTP_PROXY", proxy_url)
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setenv("NO_PROXY", "")
        # Also defeat OS-specific loopback bypass; a local fake proxy receives no real secret.
        monkeypatch.setattr("urllib.request.proxy_bypass", lambda host: False)
        client = load().Client(f"http://127.0.0.1:{direct.server_port}", "x" * 32, "sha")
        client.check_identity()
        assert routed == [(direct.server_port, "Bearer " + "x" * 32)]
    finally:
        for server, thread in zip(servers, threads, strict=True):
            server.shutdown()
            server.server_close()
            thread.join()


@pytest.mark.parametrize("kind", ["disconnect", "reset", "incomplete", "json"])
def test_ambiguous_response_queries_original_receipt(kind, tmp_path):
    from http.client import IncompleteRead, RemoteDisconnected

    errors = {
        "disconnect": RemoteDisconnected("closed"),
        "reset": ConnectionResetError(),
        "incomplete": IncompleteRead(b"partial"),
        "json": json.JSONDecodeError("truncated", "{", 1),
    }
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")
    sent = []

    def post(path, payload):
        sent.append(payload)
        raise errors[kind]

    client.post = post
    client.get = lambda path: {
        "command_id": sent[0]["command_id"],
        "result": {"instance_id": "original"},
    }
    assert client.command("START", "definition", {})["instance_id"] == "original"
    assert len(sent) == 1


def test_command_is_durable_before_transmission(tmp_path):
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha", journal_dir=tmp_path)

    def post(path, payload):
        assert (
            json.loads((tmp_path / (payload["command_id"] + ".json")).read_text())["request"]
            == payload
        )
        raise ConnectionResetError()

    client.post = post
    client.get = lambda path: (_ for _ in ()).throw(URLError("still offline"))
    with pytest.raises(RuntimeError, match="command_id"):
        client.command("START", "definition", {})
    assert len(list(tmp_path.glob("*.json"))) == 1


@pytest.mark.parametrize("code", [400, 401, 403, 409])
def test_deterministic_rejection_never_queries_or_retries(code, tmp_path):
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha", journal_dir=tmp_path)
    sent = []

    def post(path, request):
        sent.append(request)
        raise HTTPError(path, code, "rejected", {}, None)

    client.post = post
    client.get = lambda path: pytest.fail("4xx must not be retried")
    with pytest.raises(HTTPError) as error:
        client.command("START", "definition", {})
    assert error.value.code == code and len(sent) == 1


def test_durable_command_survives_new_client_and_rejects_overwrite(tmp_path):
    probe = load()
    client = probe.Client("http://127.0.0.1:8135", "x" * 32, "sha", journal_dir=tmp_path)
    request = {
        "command_id": "dd550f88-479c-4da5-9718-228e32aba261",
        "action": "START",
        "target": "definition",
        "payload": {},
    }
    client.post = lambda *args: (_ for _ in ()).throw(ConnectionResetError("secret-detail"))
    client.get = lambda path: (_ for _ in ()).throw(URLError("secret-detail"))
    with pytest.raises(RuntimeError) as error:
        client.submit(request)
    assert request["command_id"] in str(error.value) and "secret-detail" not in str(error.value)
    record = json.loads((tmp_path / (request["command_id"] + ".json")).read_text())
    assert record["request"] == request and "xxxxxxxx" not in json.dumps(record)
    second = probe.Client("http://127.0.0.1:8135", "x" * 32, "sha", journal_dir=tmp_path)
    second.get = lambda path: {
        "command_id": request["command_id"],
        "result": {"instance_id": "original"},
    }
    second.post = lambda *args: pytest.fail("committed command must not be sent again")
    assert second.recover(request["command_id"])["result"]["instance_id"] == "original"
    with pytest.raises(ValueError, match="different"):
        second.submit({**request, "target": "other-definition"})
    assert json.loads((tmp_path / (request["command_id"] + ".json")).read_text()) == record


def test_default_cli_client_also_persists_before_send(tmp_path):
    client = load().Client("http://127.0.0.1:8135", "x" * 32, "sha")

    def post(path, request):
        saved = tmp_path / "var/flowable-poc/commands" / (request["command_id"] + ".json")
        assert json.loads(saved.read_text())["request"] == request
        return {"command_id": request["command_id"], "result": {}}

    client.post = post
    client.command("START", "definition", {})


def restart_records():
    state = {
        "revision": "sha",
        "boot_id": "old",
        "timer_due_at": "2026-11-05T10:01:00+00:00",
        "prepared_at": "2026-11-05T10:00:00+00:00",
        "stop_evidence": {
            "container_id": "old-container",
            "project": "logix-flowable-poc",
            "service": "runner",
            "running": False,
            "finished_at": "2026-11-05T10:00:10+00:00",
            "observed_at": "2026-11-05T10:00:11+00:00",
        },
    }
    info = {
        "poc": True,
        "build_revision": "sha",
        "boot_id": "new",
        "boot_started_at": "2026-11-05T10:01:10+00:00",
    }
    timer = {"completed_at": "2026-11-05T10:01:11+00:00"}
    return state, info, timer


@pytest.mark.parametrize(
    "bad",
    [
        "same_boot",
        "no_stop",
        "expired_before_stop",
        "completed_before_boot",
        "running",
        "wrong_project",
        "unobserved",
        "boot_before_due",
    ],
)
def test_restart_evidence_rejects_false_positive(bad):
    state, info, timer = restart_records()
    if bad == "same_boot":
        info["boot_id"] = "old"
    elif bad == "no_stop":
        state.pop("stop_evidence")
        state["stop_observed_at"] = "2026-11-05T10:00:11+00:00"
    elif bad == "expired_before_stop":
        state["stop_evidence"]["finished_at"] = "2026-11-05T10:01:01+00:00"
    elif bad == "completed_before_boot":
        timer["completed_at"] = "2026-11-05T10:01:09+00:00"
    elif bad == "running":
        state["stop_evidence"]["running"] = True
    elif bad == "wrong_project":
        state["stop_evidence"]["project"] = "pms"
    elif bad == "unobserved":
        state["stop_evidence"].pop("observed_at")
    else:
        info["boot_started_at"] = "2026-11-05T10:00:59+00:00"
    with pytest.raises(ValueError):
        load().validate_restart(state, info, timer)


def test_restart_evidence_accepts_observed_offline_expiry():
    load().validate_restart(*restart_records())


def test_after_without_restart_rejects_before_mutating_pending_task(tmp_path):
    probe = load()
    state, info, _ = restart_records()
    info["boot_id"] = "old"
    state.update(
        {
            "pending_id": "pending",
            "pending_command": {
                "command_id": "dd550f88-479c-4da5-9718-228e32aba261",
                "action": "START",
                "target": "definition",
                "payload": {},
            },
        }
    )
    path = tmp_path / "state.json"
    probe.save_state(path, state)
    client = probe.Client("http://127.0.0.1:8135", "x" * 32, "sha")
    client.get = lambda path: info
    client.post = lambda *args: pytest.fail("invalid restart evidence must fail before commands")
    with pytest.raises(ValueError, match="boot"):
        probe.after(client, path)
    assert "verified" not in json.loads(path.read_text())


def test_controlled_restart_rejects_already_completed_timer_before_docker(tmp_path, monkeypatch):
    probe = load()
    state, info, _ = restart_records()
    state.pop("stop_evidence")
    state["boot_id"] = info["boot_id"]
    state["timer_id"] = "expired"
    path = tmp_path / "expired.json"
    probe.save_state(path, state)
    client = probe.Client("http://127.0.0.1:8135", "x" * 32, "sha")
    client.get = lambda path: info if path == "/info" else {"status": "COMPLETED"}
    monkeypatch.setattr(
        probe.subprocess, "run", lambda *a, **k: pytest.fail("must not operate Docker")
    )
    with pytest.raises(ValueError, match="pending"):
        probe.controlled_restart(client, path, "runner")


def test_container_observation_uses_daemon_clock_not_host_clock(monkeypatch):
    probe = load()
    state = {"project": "logix-flowable-poc", "service": "runner", "running": False}
    responses = iter([json.dumps(state), "2026-11-05T10:00:11.123456789Z"])
    monkeypatch.setattr(probe, "docker_call", lambda args: next(responses))
    observed = probe.runner_state("isolated-container")
    assert observed["observed_at"] == "2026-11-05T10:00:11.123456789Z"


@pytest.mark.parametrize("fault", ["disconnect", "truncated"])
def test_real_socket_response_loss_recovers_one_committed_command(fault, tmp_path):
    import socket
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    requests = []
    receipts = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            command = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(command)
            receipts[command["command_id"]] = {
                "command_id": command["command_id"],
                "result": {"instance_id": "only-instance"},
            }
            if fault == "truncated":
                self.send_response(200)
                self.send_header("Content-Length", "500")
                self.end_headers()
                self.wfile.write(b'{"command_id":')
                self.wfile.flush()
            self.connection.shutdown(socket.SHUT_RDWR)
            self.connection.close()

        def do_GET(self):
            command_id = self.path.rsplit("/", 1)[-1]
            body = json.dumps(receipts[command_id]).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        probe = load()
        url = f"http://127.0.0.1:{server.server_port}"
        client = probe.Client(url, "x" * 32, "sha", journal_dir=tmp_path)
        assert client.command("START", "definition", {}) == {"instance_id": "only-instance"}
        assert len(requests) == 1
        command_id = requests[0]["command_id"]
        second = probe.Client(url, "x" * 32, "sha", journal_dir=tmp_path)
        assert second.recover(command_id)["result"] == {"instance_id": "only-instance"}
        assert len(requests) == 1 and len(receipts) == 1
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_state_file_has_no_credentials(tmp_path):
    probe = load()
    path = tmp_path / "state.json"
    probe.save_state(path, {"run_id": "example", "cursor": 2})
    state = json.loads(path.read_text())
    assert state == {"run_id": "example", "cursor": 2}
    with pytest.raises(ValueError):
        probe.save_state(path, {"token": "secret"})
