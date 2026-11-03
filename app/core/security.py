"""认证与授权的基础设施。

刻意只用标准库实现：
- 口令：PBKDF2-HMAC-SHA256（`hashlib.pbkdf2_hmac`），不引入 passlib / bcrypt
- 令牌：HMAC-SHA256 签名的无状态票据，不引入 PyJWT

这样 requirements.txt 不用变，内网离线部署也不会有额外的编译依赖。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from typing import Optional, Tuple

_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"

# 生产环境必须通过环境变量覆盖；默认值只用于本地开发
DEV_SECRET = "logix-pms-dev-secret-change-me"
_SECRET = os.getenv("SECRET_KEY", DEV_SECRET)
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", str(12 * 3600)))


def using_dev_secret() -> bool:
    return _SECRET == DEV_SECRET


# ------------------------------------------------------------------ 口令


def hash_password(password: str) -> str:
    """返回 pbkdf2_sha256$迭代次数$salt$hash 形式的字符串。"""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS
    )
    return f"{_ALGO}${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iterations, salt, expected = stored.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


# ------------------------------------------------------------------ 令牌


def _sign(payload: str) -> str:
    return hmac.new(_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


# 演示账号口令。生产改密、建用户、bootstrap 都拒绝再次使用。
DEMO_PASSWORDS = frozenset({"admin123", "manager123", "chen123", "viewer123"})


def validate_password_strength(password: str) -> Optional[str]:
    """不合规时返回原因，合规返回 None。"""
    if len(password) < 8:
        return "口令至少 8 位"
    if password in DEMO_PASSWORDS:
        return "不能使用演示口令"
    return None


def create_token(
    user_id: int, token_version: int = 0, ttl: int = TOKEN_TTL_SECONDS
) -> Tuple[str, int]:
    """返回 (token, 过期时间戳)。

    载荷带 token_version。改密或管理员重置口令后版本 +1，旧票据立即失效。
    """
    expires = int(time.time()) + ttl
    payload = f"{user_id}.{expires}.{int(token_version)}"
    raw = f"{payload}.{_sign(payload)}"
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii"), expires


def parse_token(token: str) -> Optional[Tuple[int, int]]:
    """校验令牌并返回 (user_id, token_version)；过期或签名不对返回 None。"""
    try:
        raw = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        payload, signature = raw.rsplit(".", 1)
        user_id_str, expires_str, version_str = payload.split(".")
        if not hmac.compare_digest(signature, _sign(payload)):
            return None
        if int(expires_str) < int(time.time()):
            return None
        return int(user_id_str), int(version_str)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return None
