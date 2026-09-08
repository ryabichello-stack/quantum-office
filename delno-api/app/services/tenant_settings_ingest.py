"""E1.8 — sync tenant cabinet settings into delno-knowledge (office-assistant channel)."""

from __future__ import annotations

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.principals import PRINCIPAL_ADMIN
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.events import emit_event


def _assistant_name(settings: dict) -> str:
    return str(settings.get("assistant_name") or "DELNO")


def sync_tenant_settings_to_brain(db: Session, tenant: Tenant, *, source: str = "tenant.settings") -> dict:
    settings = get_settings()
    base = (settings.knowledge_base_url or "").strip()
    if not base:
        return {"ok": False, "skipped": True, "reason": "knowledge_disabled"}

    tenant_settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    url = f"{base.rstrip('/')}/api/brain/tenant/settings-sync"
    payload = {
        "tenant_id": tenant.slug,
        "tenant_name": tenant.name,
        "settings": tenant_settings,
        "assistant_name": _assistant_name(tenant_settings),
    }
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenant.slug,
        "X-Principal-Id": PRINCIPAL_ADMIN,
    }

    try:
        with httpx.Client(timeout=20.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                emit_event(
                    db,
                    tenant_id=tenant.id,
                    event_type="knowledge.settings_sync_failed",
                    category="operational",
                    source=source,
                    payload={"status": response.status_code, "detail": response.text[:300]},
                )
                return {"ok": False, "status": response.status_code, "detail": response.text[:300]}
            data = response.json()
    except httpx.HTTPError as exc:
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="knowledge.settings_sync_failed",
            category="operational",
            source=source,
            payload={"error": str(exc)[:300]},
        )
        return {"ok": False, "error": str(exc)}

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="knowledge.settings_synced",
        category="operational",
        source=source,
        payload={"document_id": data.get("document_id")},
    )
    return {"ok": True, **data}


def sync_tenant_settings_for_ctx(db: Session, ctx: TenantContext, *, source: str = "tenant.settings") -> dict:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one_or_none()
    if not tenant:
        return {"ok": False, "reason": "tenant_not_found"}
    return sync_tenant_settings_to_brain(db, tenant, source=source)
