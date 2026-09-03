"""E2 — Telegram adapter and inbound message recording."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.channels.telegram import TelegramAdapter
from app.models.channel_account import ChannelAccount
from app.models.conversation import Conversation, Message
from app.models.tenant import Tenant
from app.services.channel_router import ChannelContext
from app.services.inbound_messages import find_or_create_conversation, record_inbound_message
from app.adapters.channels.base import InboundMessage


@pytest.fixture
def telegram_adapter():
    return TelegramAdapter()


def test_telegram_parse_webhook_text(telegram_adapter):
    payload = {
        "update_id": 1,
        "message": {
            "message_id": 10,
            "from": {"id": 99, "first_name": "Anna", "last_name": "S", "username": "anna_s"},
            "chat": {"id": 12345, "type": "private"},
            "text": "  Привет  ",
        },
    }
    msgs = telegram_adapter.parse_webhook(payload)
    assert len(msgs) == 1
    assert msgs[0].external_user_id == "12345"
    assert msgs[0].text == "Привет"
    assert msgs[0].display_name == "Anna S"
    assert msgs[0].username == "anna_s"


def test_telegram_parse_webhook_ignores_empty(telegram_adapter):
    assert telegram_adapter.parse_webhook({"update_id": 2}) == []
    assert telegram_adapter.parse_webhook({"message": {"chat": {"id": 1}}}) == []


def test_telegram_verify_webhook_secret(telegram_adapter):
    assert telegram_adapter.verify_webhook_secret(secret_header=None, expected_secret=None)
    assert telegram_adapter.verify_webhook_secret(secret_header="abc", expected_secret="abc")
    assert not telegram_adapter.verify_webhook_secret(secret_header="wrong", expected_secret="abc")


def test_record_inbound_creates_conversation_and_message():
    tenant_id = uuid.uuid4()
    ctx = ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="demo",
        channel_type="telegram",
        principal_id="service:delno-text-guest",
        channel_account_id=uuid.uuid4(),
    )
    inbound = InboundMessage(
        channel_type="telegram",
        external_user_id="777",
        text="Нужна консультация",
        display_name="Иван",
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None

    def add_side_effect(obj):
        if isinstance(obj, Conversation):
            obj.id = uuid.uuid4()

    db.add.side_effect = add_side_effect

    with patch("app.services.inbound_messages.emit_event"):
        conv, msg = record_inbound_message(db, ctx, inbound)

    assert conv.channel == "telegram"
    assert conv.contact_ref == "tg:777"
    assert msg.role == "user"
    assert msg.body == "Нужна консультация"
    db.add.assert_called()


def test_find_or_create_reuses_existing_conversation():
    tenant_id = uuid.uuid4()
    ctx = ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="demo",
        channel_type="telegram",
        principal_id="guest",
    )
    existing = Conversation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        channel="telegram",
        contact_ref="tg:42",
        meta={"visitor_name": "Old"},
    )
    inbound = InboundMessage(channel_type="telegram", external_user_id="42", text="Hi")

    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = existing

    conv = find_or_create_conversation(db, ctx, inbound)
    assert conv is existing
    db.add.assert_not_called()
