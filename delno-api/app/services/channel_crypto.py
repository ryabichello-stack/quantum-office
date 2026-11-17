"""Encrypt bot credentials at rest using the deployment's JWT secret.

The JWT secret is already required to be unique per deployment. A separate
domain prefix keeps these ciphertexts independent of JWT signing material.
"""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

PREFIX = "fernet:v1:"


def _cipher() -> Fernet:
    secret = (get_settings().jwt_secret or "").strip()
    if not secret or secret == "change-me-in-production":
        raise RuntimeError("secure_jwt_secret_required")
    key = hashlib.sha256(("delno-channel-credentials-v1:" + secret).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt(value: str) -> str:
    return PREFIX + _cipher().encrypt(value.encode()).decode()


def decrypt(value: str | None) -> str:
    text = str(value or "")
    if not text.startswith(PREFIX):
        return text  # Legacy rows; migration must rewrite them before launch.
    try:
        return _cipher().decrypt(text[len(PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError("channel_credential_decryption_failed") from exc


def bot_token(credentials: dict | None) -> str:
    row = credentials if isinstance(credentials, dict) else {}
    return decrypt(row.get("bot_token") or row.get("access_token"))
