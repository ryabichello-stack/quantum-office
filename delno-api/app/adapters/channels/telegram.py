"""Telegram Bot API adapter (E2.2 instant bot MVP)."""

from __future__ import annotations

import secrets
from typing import Any

import httpx

from app.adapters.channels.base import InboundMessage, OutboundMessage


class TelegramAdapter:
    channel_type = "telegram"

    def parse_webhook(self, payload: dict[str, Any]) -> list[InboundMessage]:
        message = payload.get("message") or payload.get("edited_message")
        if not isinstance(message, dict):
            return []

        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return []

        text = (message.get("text") or message.get("caption") or "").strip()
        if not text:
            return []

        sender = message.get("from") or {}
        parts = [sender.get("first_name"), sender.get("last_name")]
        display_name = " ".join(p for p in parts if p).strip() or None
        username = sender.get("username")

        return [
            InboundMessage(
                channel_type=self.channel_type,
                external_user_id=str(chat_id),
                text=text,
                display_name=display_name,
                username=username,
                raw=payload,
            )
        ]

    def verify_webhook_secret(self, *, secret_header: str | None, expected_secret: str | None) -> bool:
        if not expected_secret:
            return True
        if not secret_header:
            return False
        return secrets.compare_digest(secret_header, expected_secret)

    def send_reply(
        self,
        *,
        external_user_id: str,
        message: OutboundMessage,
        credentials: dict[str, Any],
    ) -> dict[str, Any]:
        token = (credentials.get("bot_token") or "").strip()
        if not token:
            return {"ok": False, "error": "missing_bot_token"}

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        body = {"chat_id": external_user_id, "text": message.text[:4096]}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(url, json=body)
                data = response.json()
                if response.status_code != 200 or not data.get("ok"):
                    return {"ok": False, "status": response.status_code, "detail": data}
                return {"ok": True, "message_id": data.get("result", {}).get("message_id")}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc)[:300]}
