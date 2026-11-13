"""E2.4 — Branded MAX bot connect wizard (client-owned bot token)."""

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
from app.services.channel_webhooks import webhook_url_for_account
from app.services.events import emit_event

ACCESS_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{16,256}$")
WEBHOOK_SECRET_RE = re.compile(r"^[A-Za-z0-9_-]{5,256}$")
MAX_UPDATE_TYPES = ["message_created", "bot_started"]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _max_api_base() -> str:
    settings = get_settings()
    return (getattr(settings, "max_api_base_url", None) or "https://platform-api2.max.ru").strip().rstrip("/")


def _make_webhook_secret() -> str:
    for _ in range(8):
        candidate = secrets.token_urlsafe(24).replace(".", "x")[:32]
        if WEBHOOK_SECRET_RE.match(candidate):
            return candidate
    return "delno-" + secrets.token_hex(8)


def _max_request(
    token: str,
    method: str,
    *,
    http_method: str = "GET",
    params: dict[str, Any] | None = None,
    json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    url = f"{_max_api_base()}/{method.lstrip('/')}"
    headers = {"Authorization": token}
    if json is not None:
        headers["Content-Type"] = "application/json"
    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.request(http_method, url, headers=headers, params=params, json=json)
            data = response.json() if response.content else {}
            if response.status_code != 200:
                return {"ok": False, "status": response.status_code, "detail": data}
            if isinstance(data, dict) and data.get("success") is False:
                return {"ok": False, "detail": data}
            return {"ok": True, "result": data}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": str(exc)[:300]}


def validate_access_token(token: str) -> dict[str, Any]:
    cleaned = token.strip()
    if not ACCESS_TOKEN_RE.match(cleaned):
        return {"ok": False, "error": "invalid_token_format"}
    result = _max_request(cleaned, "me")
    if not result.get("ok"):
        return {"ok": False, "error": "max_get_me_failed", "detail": result.get("detail") or result.get("error")}
    bot = result.get("result") or {}
    if bot.get("is_bot") is False:
        return {"ok": False, "error": "not_a_bot"}
    return {
        "ok": True,
        "bot_id": bot.get("user_id"),
        "username": bot.get("username"),
        "first_name": bot.get("first_name") or bot.get("name"),
        "description": bot.get("description"),
    }


def _find_tenant_max(db: Session, tenant_id: UUID) -> ChannelAccount | None:
    return (
        db.query(ChannelAccount)
        .filter(ChannelAccount.tenant_id == tenant_id, ChannelAccount.type == "max")
        .order_by(ChannelAccount.created_at.desc())
        .first()
    )


def _token_used_by_other_tenant(db: Session, token: str, tenant_id: UUID) -> bool:
    rows = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.type == "max",
            ChannelAccount.status == "active",
            ChannelAccount.tenant_id != tenant_id,
        )
        .all()
    )
    for row in rows:
        creds = row.credentials_encrypted if isinstance(row.credentials_encrypted, dict) else {}
        stored = str(creds.get("bot_token") or creds.get("access_token") or "")
        if stored == token:
            return True
    return False


def public_channel_account(account: ChannelAccount) -> dict[str, Any]:
    meta = account.meta if isinstance(account.meta, dict) else {}
    channel_type = account.type or "telegram"
    return {
        "id": str(account.id),
        "type": channel_type,
        "status": account.status,
        "bot_username": meta.get("bot_username"),
        "bot_name": meta.get("bot_name"),
        "webhook_url": meta.get("webhook_url") or webhook_url_for_account(account.id, channel_type),
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
    return {"items": [public_channel_account(row) for row in rows], "total": len(rows)}


def connect_max_branded(db: Session, ctx: TenantContext, access_token: str) -> dict[str, Any]:
    validation = validate_access_token(access_token)
    if not validation.get("ok"):
        write_audit(
            db,
            ctx,
            action="channel.max.connect",
            resource="channel_account",
            result="error",
            detail=str(validation.get("error")),
        )
        return validation

    token = access_token.strip()
    if _token_used_by_other_tenant(db, token, ctx.tenant_id):
        write_audit(
            db,
            ctx,
            action="channel.max.connect",
            resource="channel_account",
            result="error",
            detail="token_already_linked",
        )
        return {"ok": False, "error": "token_already_linked"}

    account = _find_tenant_max(db, ctx.tenant_id)
    if not account:
        account = ChannelAccount(tenant_id=ctx.tenant_id, type="max", status="pending")
        db.add(account)
        db.flush()

    webhook_secret = _make_webhook_secret()
    webhook_url = webhook_url_for_account(account.id, "max")
    hook = _max_request(
        token,
        "subscriptions",
        http_method="POST",
        json={"url": webhook_url, "update_types": MAX_UPDATE_TYPES, "secret": webhook_secret},
    )
    if not hook.get("ok"):
        write_audit(
            db,
            ctx,
            action="channel.max.connect",
            resource=str(account.id),
            result="error",
            detail="set_webhook_failed",
        )
        db.commit()
        return {"ok": False, "error": "set_webhook_failed", "detail": hook.get("detail") or hook.get("error")}

    username = validation.get("username")
    account.status = "active"
    account.verified_at = _utc_now()
    account.credentials_encrypted = {"bot_token": token, "access_token": token}
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
        event_type="channel.max.connected",
        category="domain",
        source="channel.max",
        payload={
            "channel_account_id": str(account.id),
            "bot_username": username,
            "webhook_url": webhook_url,
        },
    )
    write_audit(
        db,
        ctx,
        action="channel.max.connect",
        resource=str(account.id),
        new_value={"bot_username": username, "status": "active"},
    )
    db.commit()
    return {"ok": True, "account": public_channel_account(account)}


def disconnect_max_branded(db: Session, ctx: TenantContext, account_id: UUID) -> dict[str, Any]:
    account = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.id == account_id,
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "max",
        )
        .one_or_none()
    )
    if not account:
        return {"ok": False, "error": "not_found"}

    creds = account.credentials_encrypted if isinstance(account.credentials_encrypted, dict) else {}
    token = str(creds.get("bot_token") or creds.get("access_token") or "").strip()
    meta = account.meta if isinstance(account.meta, dict) else {}
    webhook_url = str(meta.get("webhook_url") or webhook_url_for_account(account.id, "max"))
    if token:
        _max_request(token, "subscriptions", http_method="DELETE", params={"url": webhook_url})

    old_username = meta.get("bot_username")
    account.status = "disconnected"
    account.credentials_encrypted = {}
    clean_meta = dict(meta)
    clean_meta.pop("webhook_secret", None)
    account.meta = clean_meta

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="channel.max.disconnected",
        category="domain",
        source="channel.max",
        payload={"channel_account_id": str(account.id), "bot_username": old_username},
    )
    write_audit(
        db,
        ctx,
        action="channel.max.disconnect",
        resource=str(account.id),
        old_value={"bot_username": old_username, "status": "active"},
        new_value={"status": "disconnected"},
    )
    db.commit()
    return {"ok": True, "account": public_channel_account(account)}


def healthcheck_max_branded(db: Session, ctx: TenantContext, account_id: UUID) -> dict[str, Any]:
    account = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.id == account_id,
            ChannelAccount.tenant_id == ctx.tenant_id,
            ChannelAccount.type == "max",
        )
        .one_or_none()
    )
    if not account:
        return {"ok": False, "error": "not_found"}

    creds = account.credentials_encrypted if isinstance(account.credentials_encrypted, dict) else {}
    token = str(creds.get("bot_token") or creds.get("access_token") or "").strip()
    if not token:
        return {"ok": False, "error": "missing_token", "account": public_channel_account(account)}

    validation = validate_access_token(token)
    subs = _max_request(token, "subscriptions")
    subscriptions = []
    if subs.get("ok") and isinstance(subs.get("result"), dict):
        raw = subs["result"].get("subscriptions")
        if isinstance(raw, list):
            subscriptions = raw

    expected_url = webhook_url_for_account(account.id, "max")
    webhook_ok = any(isinstance(item, dict) and item.get("url") == expected_url for item in subscriptions)

    return {
        "ok": validation.get("ok") is True and webhook_ok,
        "bot": validation if validation.get("ok") else None,
        "webhook": {
            "expected_url": expected_url,
            "ok": webhook_ok,
            "subscriptions": subscriptions,
        },
        "account": public_channel_account(account),
    }
