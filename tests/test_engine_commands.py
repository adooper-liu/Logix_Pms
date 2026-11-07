"""Durable engine command identity survives a lost response and fresh DB session."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.user import User


def test_command_committed_before_send_and_same_id_recovered(client, monkeypatch):
    from app.models.engine import EngineCommand
    from app.services import engine_commands as service

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        key = str(uuid.uuid4())
        command = service.prepare(
            db, user, "SB_DEPLOY", "model:synthetic", {"xml": "synthetic"}, key
        )
        ident = command.id
        sent = []

        class Transport:
            def get(self, path):
                raise service.RemoteRejected(404)

            def post(self, path, request):
                with SessionLocal() as other:
                    assert other.get(EngineCommand, ident).request == request
                sent.append(request)
                raise ConnectionResetError()

        monkeypatch.setattr(service, "engine_client", lambda: Transport())
        service.dispatch(db, command)
        assert command.status == "UNKNOWN" and len(sent) == 1
        assert (
            service.prepare(db, user, "SB_DEPLOY", "model:synthetic", {"xml": "synthetic"}, key).id
            == ident
        )
        with pytest.raises(HTTPException) as conflict:
            service.prepare(db, user, "SB_DEPLOY", "other", {}, key)
        assert conflict.value.status_code == 409
    with SessionLocal() as db:
        command = db.get(EngineCommand, ident)
        monkeypatch.setattr(
            service,
            "engine_client",
            lambda: SimpleNamespace(
                get=lambda path: {
                    "command_id": ident,
                    "action": "SB_DEPLOY",
                    "result": {"definition_id": "def"},
                }
            ),
        )
        service.dispatch(db, command)
        assert command.receipt["result"]["definition_id"] == "def" and len(sent) == 1


def test_default_off_never_connects():
    from app.services.engine_transport import engine_client

    with pytest.raises(HTTPException) as error:
        engine_client()
    assert error.value.status_code == 503


@pytest.mark.parametrize("kind", ["redirect", "proxy", "oversize", "truncated"])
def test_real_transport_fail_closed(kind, monkeypatch):
    from http.client import IncompleteRead
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from app.services.engine_transport import EngineClient, RemoteRejected

    reached = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            reached.append(self.path)
            if kind == "redirect":
                self.send_response(302)
                self.send_header("Location", "/must-not-follow")
                self.end_headers()
            elif kind == "oversize":
                self.send_response(200)
                self.end_headers()
                try:
                    self.wfile.write(b"x" * (4 * 1024 * 1024 + 1))
                except ConnectionError:
                    pass
            elif kind == "truncated":
                self.send_response(200)
                self.send_header("Content-Length", "200")
                self.end_headers()
                self.wfile.write(b'{"partial":')
            else:
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"sandbox":true,"namespace":"sandbox","contract_version":1}')

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
        monkeypatch.setenv("no_proxy", "")
        monkeypatch.setattr("urllib.request.proxy_bypass", lambda host: False)
        transport = EngineClient(f"http://127.0.0.1:{server.server_port}", "x" * 32, "sandbox")
        if kind == "proxy":
            assert transport.check()["sandbox"] is True
        else:
            with pytest.raises((RemoteRejected, ValueError, IncompleteRead)):
                transport.get("/info")
        assert reached == ["/sandbox/v1/info"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("status", [401, 403, 500])
def test_receipt_lookup_failure_is_unknown_not_definitive_rejection(status, client, monkeypatch):
    from app.services import engine_commands as service

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "admin"))
        command = service.prepare(db, user, "SB_DEPLOY", "model:lookup", {}, str(uuid.uuid4()))
        monkeypatch.setattr(
            service,
            "engine_client",
            lambda: SimpleNamespace(
                get=lambda path: (_ for _ in ()).throw(service.RemoteRejected(status))
            ),
        )
        service.dispatch(db, command)
        assert command.status == "UNKNOWN", (
            "Cannot infer command outcome from receipt lookup failure"
        )


def test_concurrent_same_client_key_has_one_durable_intent(client):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.models.engine import EngineCommand
    from app.services import engine_commands as service

    key, gate = str(uuid.uuid4()), Barrier(2)

    def work():
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.username == "admin"))
            gate.wait(timeout=10)
            return service.prepare(db, user, "SB_DEPLOY", "model:concurrent", {}, key).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: work(), range(2)))
    assert ids[0] == ids[1]
    with SessionLocal() as db:
        assert (
            len(db.scalars(select(EngineCommand).where(EngineCommand.idempotency_key == key)).all())
            == 1
        )
