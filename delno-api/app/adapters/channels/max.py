"""MAX messenger Bot API adapter (E2.4 branded bot)."""

from __future__ import annotations

import secrets
from typing import Any

import httpx

from app.adapters.channels.base import InboundMessage, OutboundMessage
from app.core.config import get_settings


class MaxAdapter:
    channel_type = "max"

    def _api_base(self) -> str:
        settings = get_settings()
        base = (getattr(settings, "max_api_base_url", None) or "https://platform-api2.max.ru").strip().rstrip("/")
        return base

    def parse_webhook(self, payload: dict[str, Any]) -> list[InboundMessage]:
        update_type = str(payload.get("update_type") or "")
        if update_type == "message_created":
            return self._parse_message_created(payload)
        if update_type == "bot_started":
            return self._parse_bot_started(payload)
        return []

    def _parse_message_created(self, payload: dict[str, Any]) -> list[InboundMessage]:
        message = payload.get("message")
        if not isinstance(message, dict):
            return []

        sender = message.get("sender") if isinstance(message.get("sender"), dict) else {}
        if sender.get("is_bot"):
            return []

        recipient = message.get("recipient") if isinstance(message.get("recipient"), dict) else {}
        chat_id = recipient.get("chat_id")
        if chat_id is None:
            return []

        body = message.get("body") if isinstance(message.get("body"), dict) else {}
        text = str(body.get("text") or "").strip()
        if not text:
            return []

        first_name = str(sender.get("first_name") or "").strip()
        last_name = str(sender.get("last_name") or "").strip()
        display_name = " ".join(part for part in (first_name, last_name) if part).strip() or None
        username = sender.get("username")

        return [
            InboundMessage(
                channel_type=self.channel_type,
                external_user_id=str(chat_id),
                text=text,
                display_name=display_name,
                username=str(username) if username else None,
                raw=payload,
            )
        ]

    def _parse_bot_started(self, payload: dict[str, Any]) -> list[InboundMessage]:
        chat_id = payload.get("chat_id")
        if chat_id is None:
            return []
        user = payload.get("user") if isinstance(payload.get("user"), dict) else {}
        name = str(user.get("name") or user.get("first_name") or "").strip() or None
        return [
            InboundMessage(
                channel_type=self.channel_type,
                external_user_id=str(chat_id),
                text="/start",
                display_name=name,
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
        token = str(credentials.get("bot_token") or credentials.get("access_token") or "").strip()
        if not token:
            return {"ok": False, "error": "missing_bot_token"}

        try:
            chat_id = int(external_user_id)
        except ValueError:
            return {"ok": False, "error": "invalid_chat_id"}

        url = f"{self._api_base()}/messages"
        body = {"chat_id": chat_id, "text": message.text[:4000]}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(
                    url,
                    headers={"Authorization": token, "Content-Type": "application/json"},
                    json=body,
                )
                data = response.json() if response.content else {}
                if response.status_code != 200:
                    return {"ok": False, "status": response.status_code, "detail": data}
                return {"ok": True, "message": data.get("message")}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": str(exc)[:300]}
