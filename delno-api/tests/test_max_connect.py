"""E2.4 — branded MAX connect wizard."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.channel_account import ChannelAccount
from app.services import max_connect


@pytest.fixture
def ctx():
    return TenantContext(
        tenant_id=uuid.uuid4(),
        tenant_slug="salon",
        role="tenant_owner",
        user_id=uuid.uuid4(),
    )


def test_validate_access_token_rejects_bad_format():
    assert max_connect.validate_access_token("bad token")["ok"] is False


def test_validate_access_token_success():
    token = "abc123def456ghi789"
    with patch("app.services.max_connect._max_request") as mock_call:
        mock_call.return_value = {
            "ok": True,
            "result": {"user_id": 1, "username": "mybot", "first_name": "My Bot", "is_bot": True},
        }
        result = max_connect.validate_access_token(token)
    assert result["ok"] is True
    assert result["username"] == "mybot"


def test_connect_max_branded_creates_account(ctx):
    token = "abc123def456ghi789012345"
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = []

    def add_side_effect(obj):
        if isinstance(obj, ChannelAccount) and not getattr(obj, "id", None):
            obj.id = uuid.uuid4()

    db.add.side_effect = add_side_effect

    with patch("app.services.max_connect.validate_access_token") as mock_validate:
        mock_validate.return_value = {"ok": True, "username": "mybot", "first_name": "My Bot", "bot_id": 1}
        with patch("app.services.max_connect._max_request") as mock_call:
            mock_call.return_value = {"ok": True, "result": {"success": True}}
            with patch("app.services.max_connect.emit_event"):
                with patch("app.services.max_connect.write_audit"):
                    result = max_connect.connect_max_branded(db, ctx, token)

    assert result["ok"] is True
    assert result["account"]["bot_username"] == "mybot"
    assert result["account"]["status"] == "active"
    assert mock_call.call_args.kwargs["json"]["url"].endswith("/v1/webhooks/max/" + result["account"]["id"])


def test_connect_rejects_token_linked_to_other_tenant(ctx):
    token = "abc123def456ghi789012345"
    other = ChannelAccount(
        tenant_id=uuid.uuid4(),
        type="max",
        status="active",
        credentials_encrypted={"bot_token": token},
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    db.query.return_value.filter.return_value.all.return_value = [other]

    with patch("app.services.max_connect.validate_access_token") as mock_validate:
        mock_validate.return_value = {"ok": True, "username": "mybot", "first_name": "My Bot", "bot_id": 1}
        with patch("app.services.max_connect.write_audit"):
            result = max_connect.connect_max_branded(db, ctx, token)

    assert result["ok"] is False
    assert result["error"] == "token_already_linked"
