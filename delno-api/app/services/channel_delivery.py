"""E2.5 — channel outbound delivery with retry and operational events."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelAdapter, OutboundMessage
from app.services.events import emit_event

DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_RETRY_BASE_SEC = 0.5


def send_channel_reply_with_retry(
    db: Session,
    *,
    tenant_id,
    channel_type: str,
    channel_account_id,
    conversation_id,
    user_message_id,
    external_user_id: str,
    reply_text: str,
    adapter: ChannelAdapter,
    credentials: dict[str, Any],
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    retry_base_sec: float = DEFAULT_RETRY_BASE_SEC,
) -> dict[str, Any]:
    """Deliver outbound reply with bounded retries; emit delivery events."""
    last_result: dict[str, Any] = {"ok": False, "error": "not_attempted"}
    attempts = 0

    for attempt in range(1, max_attempts + 1):
        attempts = attempt
        last_result = adapter.send_reply(
            external_user_id=external_user_id,
            message=OutboundMessage(text=reply_text),
            credentials=credentials,
        )
        if last_result.get("ok"):
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="channel.message.delivered",
                category="operational",
                source=f"webhook.{channel_type}",
                payload={
                    "conversation_id": str(conversation_id),
                    "user_message_id": str(user_message_id),
                    "channel": channel_type,
                    "channel_account_id": str(channel_account_id) if channel_account_id else None,
                    "external_user_id": external_user_id,
                    "attempts": attempt,
                    "provider_message_id": last_result.get("message_id"),
                },
            )
            return {"ok": True, "attempts": attempt, "result": last_result}

        if attempt < max_attempts:
            time.sleep(retry_base_sec * attempt)

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="channel.message.delivery_failed",
        category="operational",
        source=f"webhook.{channel_type}",
        payload={
            "conversation_id": str(conversation_id),
            "user_message_id": str(user_message_id),
            "channel": channel_type,
            "channel_account_id": str(channel_account_id) if channel_account_id else None,
            "external_user_id": external_user_id,
            "attempts": attempts,
            "error": last_result.get("error") or last_result.get("detail"),
        },
    )
    return {"ok": False, "attempts": attempts, "result": last_result}
