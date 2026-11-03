"""集成密钥的可逆加密。

出站签名和入站验签都要拿回明文，所以不能只存哈希。密钥由 SECRET_KEY
派生，库里只落 `enc:v1:` 前缀的 Fernet 密文。没有前缀的历史明文仍可读取，
下次写入时换成密文。
"""

from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

PREFIX = "enc:v1:"
_DEV_SECRET = "logix-pms-dev-secret-change-me"


def _fernet() -> Fernet:
    # 导入配置以先加载 .env，再读 SECRET_KEY
    import app.core.config  # noqa: F401

    raw = os.getenv("SECRET_KEY", _DEV_SECRET)
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: Optional[str]) -> Optional[str]:
    if plain is None or plain == "":
        return plain
    if plain.startswith(PREFIX):
        return plain
    token = _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt_secret(stored: Optional[str]) -> Optional[str]:
    if stored is None or stored == "":
        return stored
    if not stored.startswith(PREFIX):
        return stored
    try:
        return _fernet().decrypt(stored[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("集成密钥无法解密，SECRET_KEY 可能已更换") from exc
