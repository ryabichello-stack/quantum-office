"""Per-tenant calendar credentials from the vault. Never reads server env tokens."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant

CALENDAR_SOURCES: dict[str, dict[str, str]] = {
    "yandex": {"vault_kind": "calendar_yandex", "auth": "caldav"},
    "mailru": {"vault_kind": "calendar_mailru", "auth": "caldav"},
    "google": {"vault_kind": "calendar_google", "auth": "token"},
    "outlook": {"vault_kind": "calendar_outlook", "auth": "token"},
}

_ALIASES = {
    "ya": "yandex",
    "yandex_calendar": "yandex",
    "mail": "mailru",
    "mail.ru": "mailru",
    "gcal": "google",
    "google_calendar": "google",
    "ms": "outlook",
    "office365": "outlook",
}

FOREIGN_CALENDAR = frozenset({"google", "outlook"})


def normalize_calendar_source(raw: str | None) -> str:
    source = (raw or "mailru").strip().lower()
    source = _ALIASES.get(source, source)
    if source not in CALENDAR_SOURCES:
        return "mailru"
    return source


def _secrets(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    blob = settings.get("secrets")
    return blob if isinstance(blob, dict) else {}


def credentials_for_calendar(db: Session, ctx: TenantContext, source: str) -> dict[str, str] | None:
    src = normalize_calendar_source(source)
    meta = CALENDAR_SOURCES[src]
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    row = _secrets(tenant).get(meta["vault_kind"])
    if not isinstance(row, dict):
        return None
    if src in FOREIGN_CALENDAR and not row.get("foreign_consent_at"):
        return None
    if meta["auth"] == "token":
        token = str(row.get("password") or "").strip()
        if not token:
            return None
        out = {"token": token}
        calendar_id = str(row.get("calendar_id") or "").strip()
        if calendar_id:
            out["calendar_id"] = calendar_id
        return out
    user = str(row.get("login") or "").strip()
    password = str(row.get("password") or "").strip()
    calendar_url = str(row.get("calendar_url") or "").strip()
    if not (user and password and calendar_url):
        return None
    out = {"username": user, "login": user, "password": password, "calendar_url": calendar_url}
    url = str(row.get("url") or "").strip()
    if url:
        out["url"] = url
    return out
