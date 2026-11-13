"""Telegram bot token via credentials.open_form / vault (PRODUCT_LOOP)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.api.v1.operator import _credential_form_kind_from_message
from app.core.tenant import TenantContext
from app.services.tenant_vault import credential_form_spec, save_secret


def test_form_spec_telegram_bot():
    form = credential_form_spec("telegram_bot")
    assert form["kind"] == "telegram_bot"
    assert form["password_required"] is True


def test_matcher_telegram_cta():
    assert (
        _credential_form_kind_from_message(
            "Открой безопасную форму credentials.open_form для telegram_bot"
        )
        == "telegram_bot"
    )
    assert (
        _credential_form_kind_from_message(
            "открой credentials.open_form", setup_next_id="telegram"
        )
        == "telegram_bot"
    )


def test_save_telegram_calls_connect():
    db = MagicMock()
    tenant = MagicMock()
    tenant.settings = {}
    db.query.return_value.filter.return_value.one.return_value = tenant
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="t", role="tenant_owner")

    with patch("app.services.tenant_vault.write_audit"), patch(
        "app.services.tenant_vault.emit_event"
    ), patch(
        "app.services.telegram_connect.connect_telegram_branded",
        return_value={
            "ok": True,
            "account": {"bot_username": "demo_bot", "status": "active", "type": "telegram"},
        },
    ) as connect:
        out = save_secret(db, ctx, kind="telegram_bot", password="123456789:AA" + ("x" * 35))

    assert out["ok"] is True
    assert out["channel_connect"]["ok"] is True
    assert "demo_bot" in (out["message"] or "")
    connect.assert_called_once()
