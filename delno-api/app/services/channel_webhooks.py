"""Shared webhook URL helpers for messenger channel accounts."""

from __future__ import annotations

from uuid import UUID

from app.core.config import get_settings


def api_public_base_url() -> str:
    settings = get_settings()
    base = (getattr(settings, "api_public_base_url", None) or settings.messenger_base_url or "").strip().rstrip("/")
    if not base:
        base = "https://api.dlno.ru"
    return base


def webhook_url_for_account(account_id: UUID, channel_type: str) -> str:
    return f"{api_public_base_url()}/v1/webhooks/{channel_type}/{account_id}"
