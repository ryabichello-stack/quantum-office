"""E2.5 — outbound delivery retry and events."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.adapters.channels.telegram import TelegramAdapter
from app.services.channel_delivery import send_channel_reply_with_retry


def test_send_channel_reply_retries_until_success():
    db = MagicMock()
    adapter = TelegramAdapter()
    tenant_id = uuid.uuid4()

    with patch.object(adapter, "send_reply", side_effect=[{"ok": False, "error": "timeout"}, {"ok": True, "message_id": 42}]):
        with patch("app.services.channel_delivery.time.sleep"):
            with patch("app.services.channel_delivery.emit_event") as mock_emit:
                result = send_channel_reply_with_retry(
                    db,
                    tenant_id=tenant_id,
                    channel_type="telegram",
                    channel_account_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    user_message_id=uuid.uuid4(),
                    external_user_id="123",
                    reply_text="Hello",
                    adapter=adapter,
                    credentials={"bot_token": "tok"},
                    max_attempts=3,
                )

    assert result["ok"] is True
    assert result["attempts"] == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "channel.message.delivered"


def test_send_channel_reply_emits_failure_after_max_attempts():
    db = MagicMock()
    adapter = TelegramAdapter()
    tenant_id = uuid.uuid4()

    with patch.object(adapter, "send_reply", return_value={"ok": False, "error": "blocked"}):
        with patch("app.services.channel_delivery.time.sleep"):
            with patch("app.services.channel_delivery.emit_event") as mock_emit:
                result = send_channel_reply_with_retry(
                    db,
                    tenant_id=tenant_id,
                    channel_type="max",
                    channel_account_id=uuid.uuid4(),
                    conversation_id=uuid.uuid4(),
                    user_message_id=uuid.uuid4(),
                    external_user_id="555",
                    reply_text="Hi",
                    adapter=adapter,
                    credentials={"bot_token": "tok"},
                    max_attempts=2,
                )

    assert result["ok"] is False
    assert result["attempts"] == 2
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "channel.message.delivery_failed"
