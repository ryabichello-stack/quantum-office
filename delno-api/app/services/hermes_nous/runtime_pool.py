"""Sticky assignment of tenants to isolated Hermes runtime slots.

Stage-0 dogfood: one Hermes container per tenant informational space
(HERMES_HOME + DELNO_MCP_KEY). Shared MCP key across tenants is forbidden —
that made quantum-labs see delno-demo setup_status.

Env (API):
  HERMES_RUNTIME_SLOTS=json list of
    {"id","base_url","api_server_key_env","mcp_key_env"}
  Defaults to tenant-a / tenant-b lab compose.
"""

from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.mcp_gateway import ensure_mcp_api_key
from app.services.hermes_nous.provision import ensure_tenant_hermes_home


def _default_slots() -> list[dict[str, str]]:
    return [
        {
            "id": "tenant-a",
            "base_url": os.environ.get("HERMES_NOUS_RUNTIME_URL")
            or "http://delno-hermes-tenant-a:8642",
            "api_server_key_env": "HERMES_API_SERVER_KEY",
            "mcp_key_env": "DELNO_MCP_KEY",  # informational — set on the container
        },
        {
            "id": "tenant-b",
            "base_url": os.environ.get("HERMES_NOUS_RUNTIME_URL_B")
            or "http://delno-hermes-tenant-b:8642",
            "api_server_key_env": "HERMES_API_SERVER_KEY_B",
            "mcp_key_env": "DELNO_MCP_KEY_B",
        },
    ]


def list_runtime_slots() -> list[dict[str, str]]:
    raw = (os.environ.get("HERMES_RUNTIME_SLOTS") or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                out = []
                for item in parsed:
                    if not isinstance(item, dict):
                        continue
                    base = str(item.get("base_url") or "").rstrip("/")
                    key_env = str(item.get("api_server_key_env") or "HERMES_API_SERVER_KEY")
                    if not base:
                        continue
                    out.append(
                        {
                            "id": str(item.get("id") or base),
                            "base_url": base,
                            "api_server_key_env": key_env,
                            "mcp_key_env": str(item.get("mcp_key_env") or ""),
                        }
                    )
                if out:
                    return out
        except json.JSONDecodeError:
            pass
    return _default_slots()


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _slot_taken_by(db: Session, slot_id: str, *, except_tenant_id: Any = None) -> str | None:
    """Return slug of another tenant already sticky on this slot, if any."""
    for tenant in db.query(Tenant).all():
        if except_tenant_id is not None and tenant.id == except_tenant_id:
            continue
        nous = _settings(tenant).get("hermes_nous")
        if not isinstance(nous, dict):
            continue
        runtime = nous.get("runtime") if isinstance(nous.get("runtime"), dict) else {}
        if str(runtime.get("slot_id") or "") == slot_id:
            return tenant.slug
    return None


def assign_isolated_runtime(db: Session, ctx: TenantContext, *, prefer_slot: str | None = None) -> dict[str, Any]:
    """Ensure this tenant has a dedicated Hermes slot + mcp_api_key.

    Sticky: once assigned, keep the same slot_id. Prefer an empty slot when new.
    """
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    ensure_mcp_api_key(db, tenant)
    db.refresh(tenant)

    slots = list_runtime_slots()
    settings = _settings(tenant)
    nous = dict(settings.get("hermes_nous") or {})
    runtime = dict(nous.get("runtime") or {})
    current_slot = str(runtime.get("slot_id") or prefer_slot or "").strip()

    chosen: dict[str, str] | None = None
    if current_slot:
        chosen = next((s for s in slots if s["id"] == current_slot), None)
    if chosen is None:
        # Prefer free slot; fall back to first.
        for slot in slots:
            if _slot_taken_by(db, slot["id"], except_tenant_id=tenant.id) is None:
                chosen = slot
                break
        if chosen is None:
            chosen = slots[0]

    record = ensure_tenant_hermes_home(
        db,
        ctx,
        runtime_base_url=chosen["base_url"],
        api_server_key_env=chosen["api_server_key_env"],
    )
    # Re-read after ensure (it rewrites runtime blob).
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    nous = dict(settings.get("hermes_nous") or {})
    runtime = dict(nous.get("runtime") or {})
    runtime.update(
        {
            "slot_id": chosen["id"],
            "runtime_base_url": chosen["base_url"],
            "api_server_key_env": chosen["api_server_key_env"],
            "mcp_key_env": chosen.get("mcp_key_env") or "",
            "isolation": "dedicated_runtime_slot",
            "profile_name": f"tenant_{tenant.slug}",
        }
    )
    nous["runtime"] = runtime
    settings["hermes_nous"] = nous
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return dict(runtime)


def ensure_tenant_runtime(db: Session, ctx: TenantContext) -> dict[str, Any]:
    """Idempotent: return assigned runtime, assigning a free slot if missing."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    nous = _settings(tenant).get("hermes_nous")
    runtime = (nous or {}).get("runtime") if isinstance(nous, dict) else None
    if isinstance(runtime, dict) and runtime.get("runtime_base_url") and runtime.get("slot_id"):
        ensure_mcp_api_key(db, tenant)
        return dict(runtime)
    return assign_isolated_runtime(db, ctx)
