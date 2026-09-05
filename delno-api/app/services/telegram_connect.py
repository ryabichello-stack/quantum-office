"""E2.3 — Branded Telegram bot connect wizard (tenant-owned bot token)."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.channel_account import ChannelAccount
from app.services.audit import write_audit
from app.services.events import emit_event

BOT_TOKEN_RE = re.compile(r"^\d{8,12}:[A-Za-z0-9_-]{30,}$")
TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def api_public_base_url() -> str:
    settings = get_settings()
    base = (getattr(settings, "api_public_base_url", None) or settings.messenger_base_url or "").strip().rstrip("/")
    if not base:
        base = "https://api.dlno.ru"
    return base


def webhook_url_for_account(account_id: UUID) -> str:
    return f"{api_public_base_url()}/v1/webhooks/telegram/{account_id}"


def _telegram_call(token: str, method: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
    url = TELEGRAM_API.format(token=token, method=method)
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=json or {})
            data = response.json()
            if response.status_code != 200 or not data.get("ok"):
                return {"ok": False, "status": response.status_code, "detail": data}
            return {"ok": True, "result": data.get("result")}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)[:300]}


def validate_bot_token(token: str) -> dict[str, Any]:
    cleaned = token.strip()
    if not BOT_TOKEN_RE.match(cleaned):
        return {"ok": False, "error": "invalid_token_format"}
    result = _telegram_call(cleaned, "getMe")
    if not result.get("ok"):
        return {"ok": False, "error": "telegram_get_me_failed", "detail": result.get("detail") or result.get("error")}
    bot = result.get("result") or {}
    return {
        "ok": True,
        "bot_id": bot.get("id"),
        "username": bot.get("username"),
        "first_name": bot.get("first_name"),
        "can_join_groups": bot.get("can_join_groups"),
    }


def _find_tenant_telegram(db: Session, tenant_id: UUID) -> ChannelAccount | None:
    return (
        db.query(ChannelAccount)
        .filter(ChannelAccount.tenant_id == tenant_id, ChannelAccount.type == "telegram")
        .order_by(ChannelAccount.created_at.desc())
        .first()
    )


def _token_used_by_other_tenant(db: Session, token: str, tenant_id: UUID) -> bool:
    rows = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.type == "telegram",
            ChannelAccount.status == "active",
            ChannelAccount.tenant_id != tenant_id,
        )
        .all()
    )
    for row in rows:
        creds = row.credentials_encrypted if isinstance(row.credentials_encrypted, dict) else {}
        if creds.get("bot_token") == token:
            return True
    return False


def _public_account(account: ChannelAccount) -> dict[str, Any]:
    meta = account.meta if isinstance(account.meta, dict) else {}
    return {
        "id": str(account.id),
        "type": account.type,
        "status": account.status,
        "bot_username": meta.get("bot_username"),
        "bot_name": meta.get("bot_name"),
        "webhook_url": meta.get("webhook_url") or webhook_url_for_account(account.id),
        "verified_at": account.verified_at.isoformat() if account.verified_at else None,
        "created_at": account.created_at.isoformat() if account.created_at else None,
    }


def list_tenant_channels(db: Session, ctx: TenantContext) -> dict[str, Any]:
    rows = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.tenant_id == ctx.tenant_id)
        .order_by(ChannelAccount.created_at.desc())
        .all()
    )
    return {"items": [_public_account(row) for row in rows], "total": len(rows)}


def connect_telegram_branded(db: Session, ctx: TenantContext, bot_token: str) -> dict[str, Any]:
    validation = validate_bot_token(bot_token)
    if not validation.get("ok"):
        write_audit(
            db,
            ctx,
            action="channel.telegram.connect",
            resource="channel_account",
            result="error",
            detail=str(validation.get("error")),
        )
        return validation

    token = bot_token.strip()
    if _token_used_by_other_tenant(db, token, ctx.tenant_id):
        write_audit(
            db,
            ctx,
            action="channel.telegram.connect",
            resource="channel_account",
            result="error",
            detail="token_already_linked",
        )
        return {"ok": False, "error": "token_already_linked"}

    account = _find_tenant_telegram(db, ctx.tenant_id)
    if not account:
        account = ChannelAccount(tenant_id=ctx.tenant_id, type="telegram", status="pending")
        db.add(account)
        db.flush()

    webhook_secret = secrets.token_urlsafe(32)
    webhook_url = webhook_url_for_account(account.id)
    hook = _telegram_call(
        token,
        "setWebhook",
        json={"url": webhook_url, "secret_token": webhook_secret, "drop_pending_updates": True},
    )
    if not hook.get("ok"):
        write_audit(
            db,
            ctx,
            action="channel.telegram.connect",
            resource=str(account.id),
            result="error",
            detail="set_webhook_failed",
        )
        db.commit()
        return {"ok": False, "error": "set_webhook_failed", "detail": hook.get("detail") or hook.get("error")}

    username = validation.get("username")
    account.status = "active"
    account.verified_at = _utc_now()
    account.credentials_encrypted = {"bot_token": token}
    account.meta = {
        "bot_username": username,
        "bot_name": validation.get("first_name"),
        "bot_id": validation.get("bot_id"),
        "webhook_secret": webhook_secret,
        "webhook_url": webhook_url,
        "mode": "branded",
    }

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="channel.telegram.connected",
        category="domain",
        source="channel.telegram",
        payload={
            "channel_account_id": str(account.id),
            "bot_username": username,
            "webhook_url": webhook_url,
        },
    )
    write_audit(
        db,
        ctx,
        action="channel.telegram.connect",
        resource=str(account.id),
        new_value={"bot_username": username, "status": "active"},
    )
    db.commit()
    return {"ok": True, "account": _public_account(account)}


def disconnect_telegram_branded(db: Session, ctx: TenantContext, account_id: UUID) -> dict[str, Any]:
    account = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.id == account_id,
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "telegram",
        )
        .one_or_none()
    )
    if not account:
        return {"ok": False, "error": "not_found"}

    creds = account.credentials_encrypted if isinstance(account.credentials_encrypted, dict) else {}
    token = str(creds.get("bot_token") or "").strip()
    if token:
        _telegram_call(token, "deleteWebhook", json={"drop_pending_updates": True})

    old_username = (account.meta or {}).get("bot_username") if isinstance(account.meta, dict) else None
    account.status = "disconnected"
    account.credentials_encrypted = {}
    meta = dict(account.meta or {}) if isinstance(account.meta, dict) else {}
    meta.pop("webhook_secret", None)
    account.meta = meta

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="channel.telegram.disconnected",
        category="domain",
        source="channel.telegram",
        payload={"channel_account_id": str(account.id), "bot_username": old_username},
    )
    write_audit(
        db,
        ctx,
        action="channel.telegram.disconnect",
        resource=str(account.id),
        old_value={"bot_username": old_username, "status": "active"},
        new_value={"status": "disconnected"},
    )
    db.commit()
    return {"ok": True, "account": _public_account(account)}


def healthcheck_telegram_branded(db: Session, ctx: TenantContext, account_id: UUID) -> dict[str, Any]:
    account = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.id == account_id,
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "telegram",
        )
        .one_or_none()
    )
    if not account:
        return {"ok": False, "error": "not_found"}

    creds = account.credentials_encrypted if isinstance(account.credentials_encrypted, dict) else {}
    token = str(creds.get("bot_token") or "").strip()
    if not token:
        return {"ok": False, "error": "missing_token", "account": _public_account(account)}

    validation = validate_bot_token(token)
    webhook = _telegram_call(token, "getWebhookInfo")
    info = webhook.get("result") if webhook.get("ok") else {}
    expected_url = webhook_url_for_account(account.id)
    webhook_ok = isinstance(info, dict) and info.get("url") == expected_url

    return {
        "ok": validation.get("ok") is True and webhook_ok,
        "bot": validation if validation.get("ok") else None,
        "webhook": {
            "url": info.get("url") if isinstance(info, dict) else None,
            "expected_url": expected_url,
            "ok": webhook_ok,
            "pending_update_count": info.get("pending_update_count") if isinstance(info, dict) else None,
        },
        "account": _public_account(account),
    }
