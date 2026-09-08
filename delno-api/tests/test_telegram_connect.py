"""E2.3 — branded Telegram connect wizard."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.channel_account import ChannelAccount
from app.services import telegram_connect


@pytest.fixture
def ctx():
    return TenantContext(
        tenant_id=uuid.uuid4(),
        tenant_slug="salon",
        role="tenant_owner",
        user_id=uuid.uuid4(),
    )


def test_validate_bot_token_rejects_bad_format():
    assert telegram_connect.validate_bot_token("not-a-token")["ok"] is False


def test_validate_bot_token_success():
    token = "123456789:AAHabcdefghijklmnopqrstuvwxyz1234567890"
    with patch("app.services.telegram_connect._telegram_call") as mock_call:
        mock_call.return_value = {
            "ok": True,
            "result": {"id": 1, "username": "mybot", "first_name": "My Bot", "can_join_groups": True},
        }
        result = telegram_connect.validate_bot_token(token)
    assert result["ok"] is True
    assert result["username"] == "mybot"


def test_connect_telegram_branded_creates_account(ctx):
    token = "123456789:AAHabcdefghijklmnopqrstuvwxyz1234567890"
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []

    account = ChannelAccount(tenant_id=ctx.tenant_id, type="telegram", status="pending")
    account.id = uuid.uuid4()

    def add_side_effect(obj):
        if isinstance(obj, ChannelAccount) and not getattr(obj, "id", None):
            obj.id = account.id

    db.add.side_effect = add_side_effect

    with patch("app.services.telegram_connect.validate_bot_token") as mock_validate:
        mock_validate.return_value = {"ok": True, "username": "mybot", "first_name": "My Bot", "bot_id": 1}
        with patch("app.services.telegram_connect._telegram_call") as mock_call:
            mock_call.return_value = {"ok": True, "result": True}
            with patch("app.services.telegram_connect.emit_event"):
                with patch("app.services.telegram_connect.write_audit"):
                    result = telegram_connect.connect_telegram_branded(db, ctx, token)

    assert result["ok"] is True
    assert result["account"]["bot_username"] == "mybot"
    assert result["account"]["status"] == "active"
    mock_call.assert_called_once()
    assert "webhooks/telegram" in mock_call.call_args.kwargs["json"]["url"]


def test_connect_rejects_token_linked_to_other_tenant(ctx):
    token = "123456789:AAHabcdefghijklmnopqrstuvwxyz1234567890"
    other = ChannelAccount(
        tenant_id=uuid.uuid4(),
        type="telegram",
        status="active",
        credentials_encrypted={"bot_token": token},
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = [other]

    with patch("app.services.telegram_connect.validate_bot_token") as mock_validate:
        mock_validate.return_value = {"ok": True, "username": "mybot", "first_name": "My Bot", "bot_id": 1}
        with patch("app.services.telegram_connect.write_audit"):
            result = telegram_connect.connect_telegram_branded(db, ctx, token)

    assert result["ok"] is False
    assert result["error"] == "token_already_linked"


def test_disconnect_clears_credentials(ctx):
    account_id = uuid.uuid4()
    account = ChannelAccount(
        id=account_id,
        tenant_id=ctx.tenant_id,
        type="telegram",
        status="active",
        credentials_encrypted={"bot_token": "123456789:AAHabcdefghijklmnopqrstuvwxyz1234567890"},
        meta={"bot_username": "mybot", "webhook_secret": "secret"},
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = account

    with patch("app.services.telegram_connect._telegram_call") as mock_call:
        with patch("app.services.telegram_connect.emit_event"):
            with patch("app.services.telegram_connect.write_audit"):
                result = telegram_connect.disconnect_telegram_branded(db, ctx, account_id)

    assert result["ok"] is True
    assert account.status == "disconnected"
    assert account.credentials_encrypted == {}
    mock_call.assert_called_once()
