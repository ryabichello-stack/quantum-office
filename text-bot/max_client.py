"""Minimal Max Bot API client (platform-api2.max.ru) for outbound send + status."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional
from urllib.parse import urlencode


def _token() -> str:
    return (os.getenv("MAX_BOT_TOKEN") or "").strip()


def _api_base() -> str:
    return (os.getenv("MAX_API_BASE") or "https://platform-api2.max.ru").rstrip("/")


def enabled() -> bool:
    flag = (os.getenv("MAX_ENABLED") or "").strip().lower() in {"1", "true", "yes"}
    return flag and bool(_token())


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "configured": bool(_token()),
        "secret_set": bool((os.getenv("MAX_BOT_SECRET") or "").strip()),
        "api_base": _api_base(),
    }


def send_text(
    *,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    text: str,
) -> dict[str, Any]:
    token = _token()
    if not token:
        raise RuntimeError("max_not_configured")
    params: dict[str, str] = {}
    if user_id:
        params["user_id"] = str(user_id)
    if chat_id:
        params["chat_id"] = str(chat_id)
    if not params:
        raise ValueError("max_send_needs_user_or_chat")
    url = f"{_api_base()}/messages?{urlencode(params)}"
    body = {"text": str(text)[:4000]}
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20.0) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"max_http_{exc.code}: {detail}") from exc
