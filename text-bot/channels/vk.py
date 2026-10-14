"""VK Callback API adapter (community messages).

Env:
  VK_ENABLED=true
  VK_GROUP_TOKEN          — community access token (messages)
  VK_CONFIRMATION_CODE    — string returned for type=confirmation
  VK_SECRET               — optional secret in callback payload
  VK_GROUP_ID             — optional, for logging
  VK_API_VERSION          — default 5.199
"""

from __future__ import annotations

import json
import logging
import os
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from channels.base import InboundMessage, env_flag, process_async

logger = logging.getLogger("ava-text-bot.vk")


def _token() -> str:
    return (os.getenv("VK_GROUP_TOKEN") or "").strip()


def _confirmation() -> str:
    return (os.getenv("VK_CONFIRMATION_CODE") or "").strip()


def _secret() -> str:
    return (os.getenv("VK_SECRET") or "").strip()


def _api_version() -> str:
    return (os.getenv("VK_API_VERSION") or "5.199").strip()


def enabled() -> bool:
    return env_flag("VK_ENABLED") and bool(_token()) and bool(_confirmation())


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "configured": bool(_token() and _confirmation()),
        "secret_set": bool(_secret()),
        "group_id": (os.getenv("VK_GROUP_ID") or "").strip() or None,
        "api_version": _api_version(),
    }


def secret_ok(payload: dict[str, Any]) -> bool:
    expected = _secret()
    if not expected:
        return True
    return str(payload.get("secret") or "") == expected


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    event_type = str(payload.get("type") or "")
    if event_type != "message_new":
        return []
    obj = payload.get("object") or {}
    message = obj.get("message") if isinstance(obj.get("message"), dict) else obj
    if not isinstance(message, dict):
        return []
    text = str(message.get("text") or "").strip()
    user_id = str(message.get("from_id") or message.get("user_id") or "").strip()
    peer_id = str(message.get("peer_id") or user_id).strip()
    if not text or not user_id:
        return []
    # Negative from_id = group; ignore outgoing echo
    try:
        if int(user_id) < 0:
            return []
    except ValueError:
        pass
    chat_type = "group" if peer_id and peer_id != user_id else "private"
    return [
        InboundMessage(
            channel="vk",
            user_id=user_id,
            text=text,
            reply_to=peer_id,
            chat_type=chat_type,
            raw=message,
        )
    ]


def send_text(peer_id: str, text: str) -> dict[str, Any]:
    token = _token()
    if not token:
        raise RuntimeError("vk_not_configured")
    params = {
        "access_token": token,
        "v": _api_version(),
        "peer_id": str(peer_id),
        "message": str(text)[:4096],
        "random_id": random.randint(1, 2_000_000_000),
    }
    url = "https://api.vk.com/method/messages.send?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        data = json.loads(resp.read().decode("utf-8") or "{}")
    if data.get("error"):
        raise RuntimeError(str(data["error"])[:300])
    return data


def _send_reply(msg: InboundMessage, reply: str) -> None:
    try:
        send_text(msg.reply_to or msg.user_id, reply)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        logger.error("vk send HTTP %s: %s", exc.code, err)
        raise


def handle_callback(payload: dict[str, Any], *, secretary_handle: Any) -> tuple[str, int]:
    """
    Returns (body, http_status).
    VK expects plain ``ok`` for events and confirmation code for type=confirmation.
    """
    event_type = str(payload.get("type") or "")
    if event_type == "confirmation":
        code = _confirmation()
        if not code:
            return "not_configured", 503
        return code, 200

    if not enabled():
        return "disabled", 503
    if not secret_ok(payload):
        return "bad_secret", 403

    messages = parse_inbound(payload)
    for msg in messages:
        process_async(msg, send_reply=_send_reply, secretary_handle=secretary_handle)
    return "ok", 200
