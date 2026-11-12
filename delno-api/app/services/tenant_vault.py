"""Tenant secrets vault (settings.secrets) — never echo plaintext back."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.audit import write_audit
from app.services.events import emit_event

SUPPORTED_KINDS = frozenset({"mango_sip"})

MANGO_SIP_FORM = {
    "kind": "mango_sip",
    "title": "SIP Mango — безопасный ввод",
    "hint": "Пароль не попадёт в ленту чата. Сохраняется только в кабинете tenant.",
    "fields": [
        {"name": "login", "label": "Логин / extension", "type": "text", "autocomplete": "username"},
        {"name": "password", "label": "SIP-пароль", "type": "password", "autocomplete": "current-password"},
    ],
    "submit_label": "Сохранить безопасно",
}


def credential_form_spec(kind: str = "mango_sip", *, prefill: dict[str, str] | None = None) -> dict[str, Any]:
    if kind != "mango_sip":
        kind = "mango_sip"
    form = dict(MANGO_SIP_FORM)
    form["kind"] = kind
    if prefill:
        # only non-secret prefill to the client
        safe = {}
        if prefill.get("login"):
            safe["login"] = prefill["login"][:120]
        form["prefill"] = safe
    return form


def looks_like_credential_paste(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 400:
        return False
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == 1:
        # single line password-ish: length + mixed charset, no spaces
        s = lines[0]
        if " " in s or len(s) < 8:
            return False
        classes = sum(
            [
                any(c.islower() for c in s),
                any(c.isupper() for c in s),
                any(c.isdigit() for c in s),
                any(not c.isalnum() for c in s),
            ]
        )
        return classes >= 3 and not any(w in s.lower() for w in ("http", "www.", ".ru", ".com"))
    if 2 <= len(lines) <= 4:
        # login + password block
        joined = " ".join(lines).lower()
        if any(w in joined for w in ("добавь", "найди", "какой", "скажи", "привет", "настрой")):
            return False
        pw = max(lines, key=len)
        return len(pw) >= 6 and " " not in pw
    return False


def parse_credential_paste(message: str) -> dict[str, str]:
    lines = [ln.strip() for ln in (message or "").splitlines() if ln.strip()]
    if not lines:
        return {}
    if len(lines) == 1:
        return {"password": lines[0][:200]}
    # Prefer last line as password, first as login
    return {"login": lines[0][:120], "password": lines[-1][:200]}


def wants_sip_secret_form(message: str) -> bool:
    lower = (message or "").lower()
    if looks_like_credential_paste(message):
        return True
    keys = (
        "sip-пароль",
        "sip пароль",
        "пароль mango",
        "пароль манго",
        "mango sip",
        "sip mango",
        "дай форму",
        "форму для парол",
        "безопасн",
    )
    if any(k in lower for k in keys):
        return True
    if "пароль" in lower and any(k in lower for k in ("sip", "mango", "манго", "линии", "телефон")):
        return True
    return False


def list_secret_status(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    blob = settings.get("secrets") if isinstance(settings.get("secrets"), dict) else {}
    items = []
    for kind in sorted(SUPPORTED_KINDS):
        row = blob.get(kind) if isinstance(blob.get(kind), dict) else {}
        items.append(
            {
                "kind": kind,
                "configured": bool(row.get("password") or row.get("login")),
                "login_masked": _mask(str(row.get("login") or "")),
                "updated_at": row.get("updated_at"),
            }
        )
    return {"items": items}


def save_secret(
    db: Session,
    ctx: TenantContext,
    *,
    kind: str,
    login: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    kind = (kind or "").strip()
    if kind not in SUPPORTED_KINDS:
        return {"ok": False, "error": "unsupported_kind"}
    login_s = (login or "").strip()
    password_s = (password or "").strip()
    if not login_s and not password_s:
        return {"ok": False, "error": "empty"}
    if password_s and len(password_s) < 4:
        return {"ok": False, "error": "password_too_short"}

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    blob = dict(settings.get("secrets") or {})
    current = dict(blob.get(kind) or {})
    old_public = {
        "login_masked": _mask(str(current.get("login") or "")),
        "has_password": bool(current.get("password")),
    }
    if login_s:
        current["login"] = login_s[:120]
    if password_s:
        current["password"] = password_s[:200]
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    blob[kind] = current
    settings["secrets"] = blob
    tenant.settings = settings

    write_audit(
        db,
        ctx,
        action="secrets.save",
        resource=f"secret:{kind}",
        old_value=old_public,
        new_value={
            "login_masked": _mask(str(current.get("login") or "")),
            "has_password": bool(current.get("password")),
        },
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="secrets.updated",
        category="operational",
        source="tenant.secrets",
        payload={"kind": kind, "configured": True},
    )
    db.commit()
    return {
        "ok": True,
        "kind": kind,
        "configured": True,
        "login_masked": _mask(str(current.get("login") or "")),
        "message": "SIP-данные сохранены в кабинете. В чат не попали.",
    }


def _mask(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 2:
        return "*" * len(value)
    if "/" in value:
        left, _, right = value.partition("/")
        return f"{left[:2]}***/{right[:1]}***" if right else f"{left[:2]}***"
    return f"{value[:2]}***{value[-1]}"
