"""Tenant-scoped knowledge document upsert (E1.8 / P2.2)."""

from __future__ import annotations

import httpx
import re

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.principals import PRINCIPAL_ADMIN
from app.models.tenant import Tenant
from app.services.events import emit_event


def _doc_id(tenant_slug: str, suffix: str) -> str:
    clean = re.sub(r"[^a-z0-9-]", "-", suffix.lower())[:40].strip("-") or "doc"
    return f"doc-{tenant_slug}-{clean}"


def upsert_tenant_knowledge_document(
    db: Session,
    tenant: Tenant,
    *,
    title: str,
    body: str,
    visibility: str = "public",
    source: str = "tenant.knowledge",
    document_id: str | None = None,
) -> dict:
    settings = get_settings()
    base = (settings.knowledge_base_url or "").strip()
    if not base:
        return {"ok": False, "skipped": True, "reason": "knowledge_disabled"}

    doc_id = document_id or _doc_id(tenant.slug, title)
    url = f"{base.rstrip('/')}/api/brain/documents/upsert"
    payload = {
        "tenant_id": tenant.slug,
        "document_id": doc_id,
        "title": title.strip(),
        "body": body.strip(),
        "visibility": visibility,
        "channels": ["office-assistant"],
        "source": source,
    }
    headers = {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenant.slug,
        "X-Principal-Id": PRINCIPAL_ADMIN,
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            response = client.post(url, json=payload, headers=headers)
            if response.status_code != 200:
                emit_event(
                    db,
                    tenant_id=tenant.id,
                    event_type="knowledge.document_failed",
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
            event_type="knowledge.document_failed",
            category="operational",
            source=source,
            payload={"error": str(exc)[:300]},
        )
        return {"ok": False, "error": str(exc)}

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="knowledge.document_upserted",
        category="operational",
        source=source,
        payload={"document_id": data.get("document_id"), "title": title[:120]},
    )
    return {"ok": True, **data}
