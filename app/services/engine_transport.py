"""Fail-closed loopback transport for the isolated sandbox; no environment proxy."""

import json
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from fastapi import HTTPException

from app.core.config import settings


class RemoteRejected(Exception):
    def __init__(self, status):
        self.status = status
        super().__init__("Sandbox request rejected")


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class EngineClient:
    def __init__(self, url, token, namespace):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost"}
            or parsed.port in {None, 8123, 8124, 8135}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or len(token) < 32
        ):
            raise HTTPException(503, "沙箱引擎地址或凭据配置无效")
        self.url, self.token, self.namespace = url.rstrip("/") + "/sandbox/v1", token, namespace
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def request(self, method, path, payload=None):
        request = Request(
            self.url + path,
            method=method,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
        )
        try:
            with self.opener.open(request, timeout=5) as response:
                body = response.read(4 * 1024 * 1024 + 1)
                if len(body) > 4 * 1024 * 1024:
                    raise ValueError("Sandbox response exceeds limit")
                value = json.loads(body)
                if not isinstance(value, dict):
                    raise ValueError("Sandbox object required")
                return value
        except HTTPError as error:
            raise RemoteRejected(error.code) from None

    def get(self, path):
        return self.request("GET", path)

    def post(self, path, payload):
        return self.request("POST", path, payload)

    def check(self):
        info = self.get("/info")
        if (
            info.get("sandbox") is not True
            or info.get("namespace") != self.namespace
            or info.get("contract_version") != 1
        ):
            raise ValueError("Sandbox identity mismatch")
        return info


def engine_client():
    if not settings.flowable_sandbox_enabled:
        raise HTTPException(503, "Flowable沙箱未启用")
    client = EngineClient(
        settings.flowable_sandbox_url,
        settings.flowable_sandbox_token,
        settings.flowable_sandbox_namespace,
    )
    client.check()
    return client
