"""Telegram Mini App (WebApp) initData validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

logger = logging.getLogger("quantum-console.tg-webapp")


def _load_bot_token() -> str:
    tok = (
        os.getenv("MINIAPP_BOT_TOKEN", "").strip()
        or os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    )
    if tok:
        return tok
    env_path = Path(
        os.getenv("TEXT_BOT_ENV_PATH", "/opt/ava-text-bot/.env")
    )
    try:
        if env_path.is_file():
            for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() == "TELEGRAM_BOT_TOKEN":
                    return val.strip().strip('"').strip("'")
    except OSError as exc:
        logger.warning("read TELEGRAM_BOT_TOKEN from %s failed: %s", env_path, exc)
    return ""


def _parse_allowed_ids() -> set[int]:
    raw = (
        os.getenv("MINIAPP_ALLOWED_IDS", "").strip()
        or os.getenv("SECRETARY_OWNER_IDS", "").strip()
    )
    if not raw:
        # Fallback: try text-bot .env
        env_path = Path(os.getenv("TEXT_BOT_ENV_PATH", "/opt/ava-text-bot/.env"))
        try:
            if env_path.is_file():
                for line in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
                    line = line.strip()
                    if line.startswith("SECRETARY_OWNER_IDS="):
                        raw = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except OSError:
            pass
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            continue
    return out


def validate_init_data(
    init_data: str,
    *,
    max_age_sec: int | None = None,
) -> dict[str, Any]:
    """Validate Telegram WebApp initData. Returns {ok, user, auth_date, error?}."""
    raw = (init_data or "").strip()
    if not raw:
        return {"ok": False, "error": "empty initData"}

    bot_token = _load_bot_token()
    if not bot_token:
        return {"ok": False, "error": "TELEGRAM_BOT_TOKEN / MINIAPP_BOT_TOKEN not configured"}

    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    got_hash = pairs.pop("hash", "")
    if not got_hash:
        return {"ok": False, "error": "missing hash"}

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expect = hmac.new(secret_key, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expect, got_hash):
        return {"ok": False, "error": "bad signature"}

    try:
        auth_date = int(pairs.get("auth_date") or "0")
    except ValueError:
        return {"ok": False, "error": "bad auth_date"}

    age = max_age_sec
    if age is None:
        age = int(os.getenv("MINIAPP_INITDATA_MAX_AGE_SEC", str(24 * 3600)))
    if age > 0 and auth_date and (time.time() - auth_date) > age:
        return {"ok": False, "error": "initData expired"}

    user: dict[str, Any] = {}
    if pairs.get("user"):
        try:
            user = json.loads(pairs["user"])
        except json.JSONDecodeError:
            return {"ok": False, "error": "bad user json"}

    user_id = user.get("id")
    try:
        user_id_int = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id_int = None

    allowed = _parse_allowed_ids()
    if allowed and (user_id_int is None or user_id_int not in allowed):
        return {
            "ok": False,
            "error": "access denied",
            "user_id": user_id_int,
        }

    return {
        "ok": True,
        "user": user,
        "user_id": user_id_int,
        "auth_date": auth_date,
        "query_id": pairs.get("query_id"),
    }


def miniapp_public_url() -> str:
    base = (
        os.getenv("CONSOLE_PUBLIC_BASE")
        or "https://a.47z.ru/_quantum_console"
    ).rstrip("/")
    return f"{base}/miniapp/"
