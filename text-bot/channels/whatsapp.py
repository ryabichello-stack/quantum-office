"""WhatsApp Cloud API (Meta) adapter.

Env:
  WHATSAPP_ENABLED=true
  WHATSAPP_TOKEN          — permanent / system user token
  WHATSAPP_PHONE_NUMBER_ID
  WHATSAPP_VERIFY_TOKEN   — for Meta webhook verification GET
  WHATSAPP_APP_SECRET     — optional X-Hub-Signature-256 check
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from channels.base import InboundMessage, env_flag, process_async

logger = logging.getLogger("ava-text-bot.whatsapp")

GRAPH_BASE = "https://graph.facebook.com/v21.0"


def _token() -> str:
    return (os.getenv("WHATSAPP_TOKEN") or "").strip()


def _phone_id() -> str:
    return (os.getenv("WHATSAPP_PHONE_NUMBER_ID") or "").strip()


def _verify_token() -> str:
    return (os.getenv("WHATSAPP_VERIFY_TOKEN") or "").strip()


def enabled() -> bool:
    return env_flag("WHATSAPP_ENABLED") and bool(_token()) and bool(_phone_id())


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "configured": bool(_token() and _phone_id()),
        "phone_number_id_set": bool(_phone_id()),
        "verify_token_set": bool(_verify_token()),
    }


def verify_webhook(mode: str, token: str, challenge: str) -> Optional[str]:
    """Meta hub.challenge handshake. Return challenge string or None."""
    if mode != "subscribe":
        return None
    expected = _verify_token()
    if not expected or token != expected:
        return None
    return challenge


def signature_ok(raw_body: bytes, header_value: str | None) -> bool:
    secret = (os.getenv("WHATSAPP_APP_SECRET") or "").strip()
    if not secret:
        return True  # optional
    if not header_value or not header_value.startswith("sha256="):
        return False
    got = header_value.split("=", 1)[1]
    expect = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(got, expect)


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    out: list[InboundMessage] = []
    for entry in payload.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                if str(msg.get("type") or "") != "text":
                    continue
                text = str((msg.get("text") or {}).get("body") or "").strip()
                wa_from = str(msg.get("from") or "").strip()
                if not text or not wa_from:
                    continue
                out.append(
                    InboundMessage(
                        channel="whatsapp",
                        user_id=wa_from,
                        text=text,
                        reply_to=wa_from,
                        chat_type="private",
                        raw=msg,
                    )
                )
    return out


def send_text(to: str, text: str) -> dict[str, Any]:
    phone_id = _phone_id()
    token = _token()
    if not phone_id or not token:
        raise RuntimeError("whatsapp_not_configured")
    url = f"{GRAPH_BASE}/{phone_id}/messages"
    body = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "text",
        "text": {"preview_url": False, "body": str(text)[:4096]},
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        return json.loads(resp.read().decode("utf-8") or "{}")


def _send_reply(msg: InboundMessage, reply: str) -> None:
    try:
        send_text(msg.reply_to or msg.user_id, reply)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:400]
        logger.error("whatsapp send HTTP %s: %s", exc.code, err)
        raise


def handle_webhook(payload: dict[str, Any], *, secretary_handle: Any) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "whatsapp_disabled", "accepted": 0}
    messages = parse_inbound(payload)
    for msg in messages:
        process_async(msg, send_reply=_send_reply, secretary_handle=secretary_handle)
    return {"ok": True, "accepted": len(messages)}
