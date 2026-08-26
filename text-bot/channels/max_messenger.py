"""MAX messenger Bot API adapter (platform-api2.max.ru).

Env:
  MAX_ENABLED=true
  MAX_BOT_TOKEN           — Authorization header token
  MAX_BOT_SECRET          — X-Max-Bot-Api-Secret for webhook verification
  MAX_API_BASE            — default https://platform-api2.max.ru
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional
from urllib.parse import urlencode

from channels.base import InboundMessage, env_flag, process_async

logger = logging.getLogger("ava-text-bot.max")


def _token() -> str:
    return (os.getenv("MAX_BOT_TOKEN") or "").strip()


def _secret() -> str:
    return (os.getenv("MAX_BOT_SECRET") or "").strip()


def _api_base() -> str:
    return (os.getenv("MAX_API_BASE") or "https://platform-api2.max.ru").rstrip("/")


def enabled() -> bool:
    return env_flag("MAX_ENABLED") and bool(_token())


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "configured": bool(_token()),
        "secret_set": bool(_secret()),
        "api_base": _api_base(),
    }


def secret_ok(header_value: str | None) -> bool:
    expected = _secret()
    if not expected:
        return True
    return hmac_safe(header_value or "", expected)


def hmac_safe(got: str, expected: str) -> bool:
    import hmac as _hmac

    return _hmac.compare_digest((got or "").strip(), expected.strip())


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Normalize Max Update object(s) into InboundMessage list."""
    items = payload if isinstance(payload, list) else [payload]
    out: list[InboundMessage] = []
    for upd in items:
        if not isinstance(upd, dict):
            continue
        update_type = str(upd.get("update_type") or upd.get("type") or "").strip()
        if update_type and update_type not in {
            "message_created",
            "message",
            "bot_started",
        }:
            # Ignore non-text events quietly.
            if update_type != "bot_started":
                continue

        message = upd.get("message") or {}
        body = message.get("body") if isinstance(message.get("body"), dict) else {}
        text = str(
            (body or {}).get("text")
            or message.get("text")
            or upd.get("text")
            or ""
        ).strip()

        sender = message.get("sender") or upd.get("user") or {}
        user_id = str(
            sender.get("user_id")
            or sender.get("id")
            or upd.get("user_id")
            or ""
        ).strip()

        recipient = message.get("recipient") or {}
        chat_id = str(
            recipient.get("chat_id")
            or message.get("chat_id")
            or upd.get("chat_id")
            or user_id
            or ""
        ).strip()

        if update_type == "bot_started" and not text:
            text = "/start"
        if not text or not user_id:
            continue

        chat_type = "group" if chat_id and chat_id != user_id else "private"
        out.append(
            InboundMessage(
                channel="max",
                user_id=user_id,
                text=text,
                reply_to=chat_id or user_id,
                chat_type=chat_type,
                raw=upd,
            )
        )
    return out


def send_text(*, user_id: Optional[str] = None, chat_id: Optional[str] = None, text: str) -> dict[str, Any]:
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
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _send_reply(msg: InboundMessage, reply: str) -> None:
    try:
        # Prefer chat_id for groups; user_id for DMs.
        if msg.chat_type == "group" and msg.reply_to:
            send_text(chat_id=msg.reply_to, text=reply)
        else:
            send_text(user_id=msg.user_id, text=reply)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        logger.error("max send HTTP %s: %s", exc.code, err)
        raise


def handle_webhook(payload: dict[str, Any], *, secretary_handle: Any) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "max_disabled", "accepted": 0}
    messages = parse_inbound(payload)
    for msg in messages:
        process_async(msg, send_reply=_send_reply, secretary_handle=secretary_handle)
    return {"ok": True, "accepted": len(messages)}
