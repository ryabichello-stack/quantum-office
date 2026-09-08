"""E2.2 — Telegram inbound auto-reply via Conversation Core."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.channels.base import InboundMessage, OutboundMessage
from app.adapters.channels.telegram import TelegramAdapter
from app.models.conversation import Conversation, Message
from app.services.channel_auto_reply import process_inbound_auto_reply
from app.services.channel_router import ChannelContext


@pytest.fixture
def channel_ctx():
    tenant_id = uuid.uuid4()
    return ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="delno-demo",
        channel_type="telegram",
        principal_id="service:delno-text-guest",
        channel_account_id=uuid.uuid4(),
    )


def test_process_inbound_auto_reply_records_and_sends(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    user_msg_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        tenant_id=channel_ctx.tenant_id,
        channel="telegram",
        contact_ref="tg:12345",
        meta={},
    )
    user_msg = Message(
        id=user_msg_id,
        tenant_id=channel_ctx.tenant_id,
        conversation_id=conversation_id,
        role="user",
        body="Сколько стоит?",
    )
    inbound = InboundMessage(
        channel_type="telegram",
        external_user_id="12345",
        text="Сколько стоит?",
        display_name="Anna",
    )
    adapter = TelegramAdapter()

    with patch(
        "app.services.channel_auto_reply.record_inbound_message",
        return_value=(conversation, user_msg),
    ):
        with patch(
            "app.services.channel_auto_reply.run_operator_turn",
            return_value={"reply": "Доставка 500 ₽", "conversation_id": str(conversation_id)},
        ):
            with patch("app.services.channel_auto_reply.emit_event"):
                with patch.object(
                    adapter,
                    "send_reply",
                    return_value={"ok": True, "message_id": 99},
                ) as mock_send:
                    result = process_inbound_auto_reply(
                        db,
                        channel_ctx,
                        inbound,
                        adapter=adapter,
                        credentials={"bot_token": "test-token"},
                    )

    assert result["conversation_id"] == str(conversation_id)
    assert result["delivered"] is True
    assert result["reply"] == "Доставка 500 ₽"
    mock_send.assert_called_once()
    call_kwargs = mock_send.call_args.kwargs
    assert call_kwargs["external_user_id"] == "12345"
    assert call_kwargs["message"] == OutboundMessage(text="Доставка 500 ₽")


def test_process_inbound_auto_reply_fallback_on_operator_error(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        tenant_id=channel_ctx.tenant_id,
        channel="telegram",
        contact_ref="tg:99",
        meta={},
    )
    user_msg = Message(
        id=uuid.uuid4(),
        tenant_id=channel_ctx.tenant_id,
        conversation_id=conversation_id,
        role="user",
        body="Hi",
    )
    inbound = InboundMessage(channel_type="telegram", external_user_id="99", text="Hi")
    adapter = TelegramAdapter()

    with patch(
        "app.services.channel_auto_reply.record_inbound_message",
        return_value=(conversation, user_msg),
    ):
        with patch(
            "app.services.channel_auto_reply.run_operator_turn",
            side_effect=RuntimeError("llm down"),
        ):
            with patch("app.services.channel_auto_reply.emit_event"):
                with patch.object(adapter, "send_reply", return_value={"ok": True}) as mock_send:
                    result = process_inbound_auto_reply(
                        db,
                        channel_ctx,
                        inbound,
                        adapter=adapter,
                        credentials={"bot_token": "tok"},
                    )

    assert result["delivered"] is True
    assert "не могу ответить" in result["reply"].lower()
    mock_send.assert_called_once()
    db.add.assert_called()
