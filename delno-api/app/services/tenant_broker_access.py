"""Decide which credential a calendar/files call may use.

Rules:
- no tenant context, or a claimed tenant that is not the caller → reject
- vault credentials of this tenant win
- server env tokens only for a tenant explicitly marked as the service account
- env token values are never copied into the result
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.calendar_accounts import credentials_for_calendar, normalize_calendar_source
from app.services.files_cloud import credentials_for_source, normalize_source

_FILE_CLOUDS = frozenset({"yadisk", "mailru", "gdrive", "onedrive"})


class TenantAccessError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def assert_same_tenant(ctx: TenantContext | None, claimed: str | None) -> None:
    if ctx is None or not getattr(ctx, "tenant_id", None):
        raise TenantAccessError("tenant_required")
    raw = (claimed or "").strip()
    if not raw:
        return
    allowed = {str(ctx.tenant_id), (ctx.tenant_slug or "").strip()}
    if raw not in allowed:
        raise TenantAccessError("tenant_mismatch")


def is_service_tenant(tenant: Tenant) -> bool:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    if settings.get("service_tenant") is True:
        return True
    marked = (get_settings().service_tenant_slug or "").strip()
    return bool(marked) and tenant.slug == marked


def _upstream_configured(kind: str, config_base_url: str) -> bool:
    if (config_base_url or "").strip():
        return True
    settings = get_settings()
    if kind == "calendar":
        return bool((settings.calendar_base_url or "").strip())
    if kind == "files":
        return bool((settings.files_base_url or "").strip())
    return False


def prepare_broker_access(
    db: Session,
    ctx: TenantContext | None,
    *,
    kind: str,
    source: str | None,
    claimed_tenant: str | None = None,
    config_base_url: str = "",
) -> dict[str, Any]:
    assert_same_tenant(ctx, claimed_tenant)
    assert ctx is not None
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    live = _upstream_configured(kind, config_base_url)
    needs_secret = True
    creds: dict[str, str] | None = None
    if kind == "calendar":
        creds = credentials_for_calendar(db, ctx, normalize_calendar_source(source))
    elif kind == "files":
        src = normalize_source(source) or (source or "")
        if src not in _FILE_CLOUDS:
            needs_secret = False
        else:
            creds = credentials_for_source(db, ctx, src)
    else:
        raise TenantAccessError("unsupported_kind")

    if creds:
        return {
            "ok": True,
            "tenant_id": str(ctx.tenant_id),
            "credentials": creds,
            "allow_env_fallback": False,
        }
    if needs_secret and is_service_tenant(tenant):
        # Flag only. The broker may read its own env. We do not copy secrets out.
        return {
            "ok": True,
            "tenant_id": str(ctx.tenant_id),
            "credentials": {"allow_env_fallback": True},
            "allow_env_fallback": True,
        }
    if needs_secret and live:
        raise TenantAccessError("tenant_credentials_required")
    return {
        "ok": True,
        "tenant_id": str(ctx.tenant_id),
        "credentials": {},
        "allow_env_fallback": False,
        "stub": not live,
    }


def apply_access(
    db: Session,
    ctx: TenantContext | None,
    config: dict[str, Any],
    *,
    kind: str,
    source: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        access = prepare_broker_access(
            db,
            ctx,
            kind=kind,
            source=source,
            config_base_url=str((config or {}).get("base_url") or ""),
        )
    except TenantAccessError as exc:
        return None, exc.code
    merged = dict(config or {})
    merged["_tenant_id"] = access["tenant_id"]
    if access.get("credentials"):
        merged["_request_credentials"] = access["credentials"]
    merged["_allow_env_fallback"] = bool(access.get("allow_env_fallback"))
    return merged, None
