"""集成密钥加密往返，以及历史明文仍可解密。"""

from __future__ import annotations

from app.core.secrets import decrypt_secret, encrypt_secret


def test_encrypt_roundtrip_and_legacy_plaintext():
    stored = encrypt_secret("test-secret")
    assert stored is not None
    assert stored.startswith("enc:v1:")
    assert decrypt_secret(stored) == "test-secret"
    assert decrypt_secret("legacy-plain") == "legacy-plain"
    assert encrypt_secret(stored) == stored
    assert encrypt_secret(None) is None
    assert decrypt_secret("") == ""
