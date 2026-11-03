"""可选的 OpenID Connect 登录。

未配置 OIDC_ISSUER 时登录入口返回 404，本地口令登录保持原样。
配置后走授权码 + PKCE。用户按 preferred_username / email 匹配已有账号，
不在这里自动开户。
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
import urllib.parse
import urllib.request
from typing import Any, Dict

import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.core.security import _sign


class OidcError(ValueError):
    pass


def enabled() -> bool:
    return bool(settings.oidc_issuer and settings.oidc_client_id)


def code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def new_verifier() -> str:
    return secrets.token_urlsafe(48)


def pack_state(verifier: str, nonce: str) -> str:
    raw = json.dumps(
        {"v": verifier, "n": nonce, "exp": int(time.time()) + 600},
        separators=(",", ":"),
    )
    blob = raw + "." + _sign(raw)
    return base64.urlsafe_b64encode(blob.encode("utf-8")).decode("ascii")


def unpack_state(state: str) -> Dict[str, Any]:
    try:
        blob = base64.urlsafe_b64decode(state.encode("ascii")).decode("utf-8")
        raw, signature = blob.rsplit(".", 1)
        if not hmac_compare(signature, _sign(raw)):
            raise OidcError("state 签名无效")
        data = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise OidcError("state 无效") from exc
    if int(data.get("exp") or 0) < int(time.time()):
        raise OidcError("state 已过期")
    return data


def hmac_compare(left: str, right: str) -> bool:
    import hmac

    return hmac.compare_digest(left, right)


def exchange_code(code: str, verifier: str, discovery: Dict[str, Any]) -> Dict[str, Any]:
    body = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.oidc_redirect_uri,
            "client_id": settings.oidc_client_id,
            "client_secret": settings.oidc_client_secret,
            "code_verifier": verifier,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        discovery["token_endpoint"],
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _discovery(fetch=urllib.request.urlopen) -> Dict[str, Any]:
    issuer = settings.oidc_issuer.rstrip("/")
    url = issuer + "/.well-known/openid-configuration"
    with fetch(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def authorization_url(state: str, nonce: str, verifier: str, discovery: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode(
        {
            "response_type": "code",
            "client_id": settings.oidc_client_id,
            "redirect_uri": settings.oidc_redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge(verifier),
            "code_challenge_method": "S256",
        }
    )
    return discovery["authorization_endpoint"] + "?" + query


def username_from_claims(claims: Dict[str, Any]) -> str:
    for key in ("preferred_username", "email", "sub"):
        value = (claims.get(key) or "").strip()
        if value:
            return value.split("@", 1)[0]
    raise OidcError("身份令牌缺少 preferred_username / email / sub")


def decode_id_token(token: str, nonce: str, jwks_url: str, jwks_client=None) -> Dict[str, Any]:
    client = jwks_client or PyJWKClient(jwks_url)
    signing_key = client.get_signing_key_from_jwt(token)
    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256", "ES256"],
        audience=settings.oidc_client_id,
        issuer=settings.oidc_issuer.rstrip("/"),
    )
    if claims.get("nonce") != nonce:
        raise OidcError("nonce 不一致")
    return claims
