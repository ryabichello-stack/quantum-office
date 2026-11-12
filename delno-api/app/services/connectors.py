"""Per-tenant office connector settings (tools-first, secrets optional later)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.connectors import CONNECTOR_KINDS, get_connector, list_connectors
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.audit import write_audit
from app.services.events import emit_event

# Keys that must never leave the API in cleartext responses.
_SECRET_KEYS = frozenset({"webhook_token", "password", "api_key", "secret", "token"})


def _tenant_connectors_blob(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    raw = settings.get("connectors")
    return raw if isinstance(raw, dict) else {}


def _public_config(config: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in config.items():
        if key in _SECRET_KEYS:
            out[key] = "***" if value else ""
        elif key == "base_url":
            out[key] = str(value or "")
        elif key == "enabled":
            out[key] = bool(value)
        else:
            # keep non-secret scalars only
            if isinstance(value, (str, int, float, bool)) or value is None:
                out[key] = value
    return out


def list_tenant_connectors(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = _tenant_connectors_blob(tenant)
    items = []
    for connector in list_connectors():
        config = blob.get(connector.kind) if isinstance(blob.get(connector.kind), dict) else {}
        status = connector.status(tenant_slug=ctx.tenant_slug, config=config)
        items.append(
            {
                "kind": connector.kind,
                "enabled": bool(config.get("enabled", False)),
                "configured": status.configured,
                "status": status.as_dict(),
                "config": _public_config(config),
            }
        )
    return {"tenant_slug": ctx.tenant_slug, "total": len(items), "items": items}


def update_tenant_connector(
    db: Session,
    ctx: TenantContext,
    kind: str,
    *,
    enabled: bool | None = None,
    base_url: str | None = None,
    webhook_token: str | None = None,
) -> dict[str, Any]:
    if kind not in CONNECTOR_KINDS:
        return {"ok": False, "error": "unknown_kind", "kind": kind}
    connector = get_connector(kind)
    if not connector:
        return {"ok": False, "error": "unknown_kind", "kind": kind}

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
    blob = dict(settings.get("connectors") or {})
    current = dict(blob.get(kind) or {})
    old_public = _public_config(current)

    if enabled is not None:
        current["enabled"] = bool(enabled)
    if base_url is not None:
        current["base_url"] = base_url.strip()
    if webhook_token is not None:
        # empty string clears
        if webhook_token.strip():
            current["webhook_token"] = webhook_token.strip()
        else:
            current.pop("webhook_token", None)

    blob[kind] = current
    settings["connectors"] = blob
    tenant.settings = settings

    status = connector.status(tenant_slug=ctx.tenant_slug, config=current)
    write_audit(
        db,
        ctx,
        action="connector.update",
        resource=f"connector:{kind}",
        old_value=old_public,
        new_value=_public_config(current),
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="connector.updated",
        category="operational",
        source="tenant.connectors",
        payload={"kind": kind, "enabled": bool(current.get("enabled", False)), "configured": status.configured},
    )
    db.commit()
    return {
        "ok": True,
        "kind": kind,
        "enabled": bool(current.get("enabled", False)),
        "configured": status.configured,
        "status": status.as_dict(),
        "config": _public_config(current),
    }


def probe_tenant_connector(db: Session, ctx: TenantContext, kind: str) -> dict[str, Any]:
    if kind not in CONNECTOR_KINDS:
        return {"ok": False, "error": "unknown_kind", "kind": kind}
    connector = get_connector(kind)
    if not connector:
        return {"ok": False, "error": "unknown_kind", "kind": kind}
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = _tenant_connectors_blob(tenant)
    config = blob.get(kind) if isinstance(blob.get(kind), dict) else {}
    result = connector.probe(tenant_slug=ctx.tenant_slug, config=config)
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="connector.probed",
        category="operational",
        source="tenant.connectors",
        payload={"kind": kind, "configured": result.configured, "ok": result.ok, "error": result.error},
    )
    db.commit()
    return result.as_dict()


def connector_config_for(db: Session, ctx: TenantContext, kind: str) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    blob = _tenant_connectors_blob(tenant)
    raw = blob.get(kind)
    return raw if isinstance(raw, dict) else {}


def list_tenant_connector_readiness(db: Session, ctx: TenantContext) -> list[dict[str, Any]]:
    """Operational readiness for this tenant, beyond a reachable shared service."""
    from app.services.files_cloud import cloud_status

    items = []
    for item in list_tenant_connectors(db, ctx).get("items") or []:
        kind = item["kind"]
        connector = get_connector(kind)
        try:
            probe = connector.probe(tenant_slug=ctx.tenant_slug, config=connector_config_for(db, ctx, kind)) if connector else None
        except Exception:
            probe = None
        health = ((probe.data or {}).get("health") or {}) if probe else {}
        service_ready = bool(item.get("enabled") and probe and probe.ok and probe.configured)
        if kind == "mail":
            service_ready = service_ready and bool(health.get("smtp_configured"))
        elif kind == "calendar":
            service_ready = service_ready and not bool(health.get("stub_mode"))
        elif kind == "conference":
            default = health.get("default_provider")
            service_ready = service_ready and any(
                p.get("provider") == default and p.get("configured")
                for p in health.get("providers") or []
            )
        if kind == "files":
            try:
                tenant_authorized = int(cloud_status(db, ctx).get("ready_count") or 0) > 0
            except Exception:
                tenant_authorized = False
        else:
            tenant_authorized = bool((probe.data or {}).get("tenant_account_verified")) if probe else False
        usable = bool(service_ready and tenant_authorized)
        items.append({
            "kind": kind,
            "enabled": bool(item.get("enabled")),
            "service_reachable": bool(probe and probe.ok),
            "service_ready": service_ready,
            "tenant_authorized": tenant_authorized,
            "usable": usable,
            "providers": [
                {"name": p.get("provider") or p.get("source"), "configured": bool(p.get("configured"))}
                for p in health.get("providers") or []
            ],
            "reason": None if usable else (probe.error if probe and probe.error else "account_or_provider_not_configured"),
        })
    return items
