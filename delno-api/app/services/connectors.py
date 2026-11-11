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
