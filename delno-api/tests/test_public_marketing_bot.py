from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.conversation import Conversation
from app.adapters.channels.base import InboundMessage
from app.services.channel_router import ChannelContext
from app.services.channel_auto_reply import _operator_reply
from app.services.channel_crypto import bot_token, decrypt, encrypt
from app.services.public_marketing_bot import answer_public_bot


@pytest.fixture(autouse=True)
def strong_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-with-enough-entropy-for-bot-tests-123")
    from app.core.config import get_settings
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_bot_token_is_encrypted_at_rest():
    token = "123456789:AAHabcdefghijklmnopqrstuvwxyz1234567890"
    stored = encrypt(token)
    assert token not in stored
    assert stored.startswith("fernet:v1:")
    assert decrypt(stored) == token
    assert bot_token({"bot_token": stored}) == token


def test_public_bot_requires_pdn_consent_before_lead():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-public", role="public")
    conversation = Conversation(id=uuid.uuid4(), tenant_id=tenant_id, channel="telegram", meta={})
    db = MagicMock()
    with patch("app.services.public_marketing_bot.create_lead_record") as create:
        with patch("app.services.public_marketing_bot._kb_snippet", return_value=""):
            first = answer_public_bot(
                db,
                ctx,
                conversation,
                message="Позвоните мне +7 921 751-51-03",
                display_name="Денис",
                source="telegram_bot",
            )
            assert "согласи" in first.lower()
            assert "privacy" in first.lower()
            create.assert_not_called()

            mid = answer_public_bot(
                db,
                ctx,
                conversation,
                message="согласен на обработку ПДн",
                display_name="Денис",
                source="telegram_bot",
            )
            assert "да, свяжитесь" in mid.lower()
            create.assert_not_called()

            lead = MagicMock(id=uuid.uuid4())
            create.return_value = (lead, {})
            second = answer_public_bot(
                db,
                ctx,
                conversation,
                message="Да, свяжитесь со мной. Денис",
                display_name="Денис",
                source="telegram_bot",
            )
            assert "передал контакт" in second.lower()
            assert "10:00" in second and "19:00" in second
            assert create.call_args.kwargs["phone"] == "+79217515103"
            assert create.call_args.args[1] == ctx
            assert create.call_args.kwargs["conversation_id"] == conversation.id


def test_public_bot_uses_kb_in_system_prompt():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-public", role="public")
    conversation = Conversation(id=uuid.uuid4(), tenant_id=tenant_id, channel="max", meta={})
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    with patch(
        "app.services.public_marketing_bot._kb_snippet",
        return_value="Тариф «Диалоги» — 2 990 ₽ / мес. Маркер KB_HIT_TEST.",
    ):
        with patch(
            "app.services.public_marketing_bot.chat_for_tenant",
            return_value={
                "ok": True,
                "data": {"choices": [{"message": {"content": "DELNO помогает отвечать клиентам."}}]},
            },
        ) as chat:
            reply = answer_public_bot(
                db, ctx, conversation, message="Что умеет DELNO?", display_name=None, source="max_bot"
            )
    assert "DELNO" in reply
    assert "tools" not in chat.call_args.kwargs
    assert chat.call_args.args[1] == ctx
    messages = chat.call_args.kwargs["messages"]
    assert "KB_HIT_TEST" in messages[0]["content"]


def test_public_route_does_not_run_merchant_agent():
    tenant_id = uuid.uuid4()
    conversation = Conversation(id=uuid.uuid4(), tenant_id=tenant_id, channel="telegram", meta={})
    ctx = ChannelContext(
        tenant_id=tenant_id, tenant_slug="delno-public", channel_type="telegram", principal_id="guest"
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = conversation
    inbound = InboundMessage(channel_type="telegram", external_user_id="100", text="Привет")
    with patch("app.services.public_marketing_bot.answer_public_bot", return_value="Здравствуйте"):
        with patch("app.services.channel_auto_reply.run_operator_turn") as merchant_agent:
            result = _operator_reply(db, ctx, inbound, conversation.id)
    assert result["reply"] == "Здравствуйте"
    merchant_agent.assert_not_called()
