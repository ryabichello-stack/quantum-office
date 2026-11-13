"""Dual-mode channel auth: bot token (existing) OR QR / user-session web login.

QR session flow (Telegram/MAX/Instagram):
1. Owner starts QR login → pending ChannelAccount (meta.auth_mode=qr_session)
2. Client scans QR / opens deep-link (provider worker fills meta.qr_url)
3. Session string/cookie confirmed → credentials_encrypted.session, status=active

Bot-token path stays in telegram_connect / max_connect.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.channel_account import ChannelAccount
from app.services.audit import write_audit
from app.services.events import emit_event


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def start_qr_login(
    db: Session,
    ctx: TenantContext,
    *,
    channel_type: str,
    label: str | None = None,
) -> dict[str, Any]:
    channel_type = channel_type.strip().lower()
    if channel_type not in {"telegram", "max", "instagram"}:
        return {"ok": False, "error": "unsupported_channel"}

    login_id = secrets.token_urlsafe(16)
    row = ChannelAccount(
        tenant_id=ctx.tenant_id,
        type=channel_type,
        status="pending_qr",
        credentials_encrypted={},
        meta={
            "auth_mode": "qr_session",
            "label": label or f"{channel_type}-qr",
            "login_id": login_id,
            "started_at": _now(),
            "qr_payload": None,
            "qr_url": None,
            "instructions_ru": (
                "Вариант A: дайте токен бота (отдельный endpoint connect). "
                "Вариант B (этот): отсканируйте QR / подтвердите web-login, "
                "затем вставьте session-строку в кабинете."
            ),
        },
    )
    db.add(row)
    db.flush()
    write_audit(
        db,
        ctx,
        action="channel.qr.start",
        resource=f"channel:{channel_type}",
        new_value={"account_id": str(row.id), "login_id": login_id},
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="channel.qr.started",
        category="operational",
        source="hermes",
        payload={"channel_type": channel_type, "account_id": str(row.id)},
    )
    db.commit()
    return {
        "ok": True,
        "auth_mode": "qr_session",
        "account_id": str(row.id),
        "login_id": login_id,
        "status": row.status,
        "channel_type": channel_type,
        "message_ru": (
            f"QR-сессия для {channel_type} создана. "
            "Когда QR-воркер будет на мосту — появится картинка. "
            "Можно завершить вставкой session (confirm)."
        ),
        "next": "scan_or_paste_session",
    }


def confirm_qr_session(
    db: Session,
    ctx: TenantContext,
    *,
    account_id: UUID,
    session_material: str,
) -> dict[str, Any]:
    row = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.id == account_id, ChannelAccount.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    if not row:
        return {"ok": False, "error": "not_found"}
    meta = dict(row.meta or {})
    if meta.get("auth_mode") != "qr_session":
        return {"ok": False, "error": "not_qr_account"}
    material = (session_material or "").strip()
    if len(material) < 20:
        return {"ok": False, "error": "session_too_short"}

    creds = dict(row.credentials_encrypted or {})
    creds["session"] = material  # TODO: encrypt with platform key
    creds["confirmed_at"] = _now()
    row.credentials_encrypted = creds
    row.status = "active"
    meta["confirmed_at"] = _now()
    row.meta = meta
    row.verified_at = datetime.now(timezone.utc)
    write_audit(
        db,
        ctx,
        action="channel.qr.confirm",
        resource=f"channel:{row.type}",
        new_value={"account_id": str(row.id), "status": "active"},
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="channel.qr.confirmed",
        category="operational",
        source="hermes",
        payload={"channel_type": row.type, "account_id": str(row.id)},
    )
    db.commit()
    return {
        "ok": True,
        "account_id": str(row.id),
        "status": row.status,
        "auth_mode": "qr_session",
        "message_ru": f"Канал {row.type} подключён через QR/session.",
    }


def qr_status(db: Session, ctx: TenantContext, *, account_id: UUID) -> dict[str, Any]:
    row = (
        db.query(ChannelAccount)
        .filter(ChannelAccount.id == account_id, ChannelAccount.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    if not row:
        return {"ok": False, "error": "not_found"}
    meta = dict(row.meta or {})
    creds = row.credentials_encrypted if isinstance(row.credentials_encrypted, dict) else {}
    return {
        "ok": True,
        "account_id": str(row.id),
        "channel_type": row.type,
        "status": row.status,
        "auth_mode": meta.get("auth_mode"),
        "login_id": meta.get("login_id"),
        "qr_url": meta.get("qr_url"),
        "has_session": bool(creds.get("session")),
        "instructions_ru": meta.get("instructions_ru"),
    }
