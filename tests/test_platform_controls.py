"""组织隔离、指标、单点登录辅助函数和对象存储。"""

from __future__ import annotations

import io

from app.services.oidc import code_challenge, pack_state, unpack_state, username_from_claims
from app.services.storage import S3Storage

API = "/api/v1"


def test_oidc_login_is_absent_until_configured(anon_client):
    response = anon_client.get(f"{API}/auth/oidc/login")
    assert response.status_code == 404


def test_oidc_state_roundtrip_and_username():
    state = pack_state("verifier-value", "nonce-value")
    unpacked = unpack_state(state)
    assert unpacked["v"] == "verifier-value"
    assert unpacked["n"] == "nonce-value"
    assert code_challenge("abc")
    assert username_from_claims({"preferred_username": "ada"}) == "ada"
    assert username_from_claims({"email": "ada@example.com"}) == "ada"


def test_s3_storage_uses_the_injected_client():
    saved = {}

    class FakeClient:
        def put_object(self, Bucket, Key, Body):
            saved["bucket"] = Bucket
            saved["key"] = Key
            saved["body"] = Body

    storage = S3Storage("bucket-a", FakeClient())
    digest, size = storage.save("docs/a.txt", io.BytesIO(b"hello"), 100)
    assert size == 5
    assert saved == {"bucket": "bucket-a", "key": "docs/a.txt", "body": b"hello"}
    assert len(digest) == 64


def test_metrics_are_plain_text(client):
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "logix_http_requests_total" in response.text
    assert response.headers["x-request-id"]


def test_project_outside_org_is_hidden_from_owner(client, owner_client):
    org = client.post(
        f"{API}/org-units",
        json={"code": "CO-WEST-TEST", "name": "西部测试公司", "type": "COMPANY"},
    )
    assert org.status_code == 201, org.text
    created = client.post(
        f"{API}/projects",
        json={
            "name": "西部隔离项目",
            "methodology": "BPI",
            "owner": "系统管理员",
            "org_unit_id": org.json()["id"],
        },
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    assert created.json()["org_unit_id"] == org.json()["id"]

    listed = owner_client.get(f"{API}/projects", params={"page_size": 200}).json()
    assert all(item["id"] != project_id for item in listed["items"])
    assert owner_client.get(f"{API}/projects/{project_id}").status_code == 404
    assert client.get(f"{API}/projects/{project_id}").status_code == 200
    assert client.delete(f"{API}/projects/{project_id}").status_code == 200


def test_audit_anchor_is_readable(client):
    response = client.get(f"{API}/audit/anchor")
    assert response.status_code == 200
    body = response.json()
    assert "hash" in body
    assert "id" in body
