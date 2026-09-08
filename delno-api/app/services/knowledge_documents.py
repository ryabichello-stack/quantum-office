"""Tenant-scoped knowledge document upsert (E1.8 / P2.2)."""

from __future__ import annotations

import httpx
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.principals import PRINCIPAL_ADMIN
from app.models.tenant import Tenant
from app.services.events import emit_event


def _doc_id(tenant_slug: str, suffix: str) -> str:
    clean = re.sub(r"[^a-z0-9-]", "-", suffix.lower())[:40].strip("-") or "doc"
    return f"doc-{tenant_slug}-{clean}"


def _brain_upsert(
    db: Session,
    tenant: Tenant,
    *,
    title: str,
    body: str,
    visibility: str,
    source: str,
    document_id: str | None,
    status: str | None = None,
    index_zone: str | None = None,
    publication: dict[str, Any] | None = None,
    event_type: str = "knowledge.document_upserted",
) -> dict:
    settings = get_settings()
    base = (settings.knowledge_base_url or "").strip()
    if not base:
        return {"ok": False, "skipped": True, "reason": "knowledge_disabled"}

    doc_id = document_id or _doc_id(tenant.slug, title)
    url = f"{base.rstrip('/')}/api/brain/documents/upsert"
    payload: dict[str, Any] = {
        "tenant_id": tenant.slug,
        "document_id": doc_id,
        "title": title.strip(),
        "body": body.strip(),
        "visibility": visibility,
        "channels": ["office-assistant"],
        "source": source,
    }
    if status:
        payload["status"] = status
    if index_zone:
        payload["index_zone"] = index_zone
    if publication:
        payload["publication"] = publication
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
        event_type=event_type,
        category="operational",
        source=source,
        payload={"document_id": data.get("document_id"), "title": title[:120]},
    )
    return {"ok": True, **data}


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
    """Legacy upsert — unchanged behavior for existing callers."""
    return _brain_upsert(
        db,
        tenant,
        title=title,
        body=body,
        visibility=visibility,
        source=source,
        document_id=document_id,
    )


def upsert_draft_knowledge(
    db: Session,
    tenant: Tenant,
    *,
    title: str,
    body: str,
    source: str = "onboarding.draft",
    document_id: str | None = None,
) -> dict:
    """Onboarding draft — company visibility, unpublished, private index zone."""
    return _brain_upsert(
        db,
        tenant,
        title=title,
        body=body,
        visibility="company",
        source=source,
        document_id=document_id,
        status="draft",
        index_zone="private",
        publication={"status": "unpublished"},
        event_type="onboarding.knowledge_draft_updated",
    )


def publish_tenant_knowledge_document(
    db: Session,
    tenant: Tenant,
    *,
    document_id: str,
    approved_by: str,
    source: str = "onboarding.publish",
    body: str | None = None,
    title: str | None = None,
) -> dict:
    """Publish a document for widget/guest retrieval (requires existing body or new body)."""
    now = datetime.now(timezone.utc).isoformat()
    if not body or not title:
        return {
            "ok": False,
            "skipped": True,
            "reason": "publish_requires_reupsert_with_body",
            "document_id": document_id,
            "hint": "Use brain get or store body in onboarding_draft before publish",
        }

    return _brain_upsert(
        db,
        tenant,
        title=title,
        body=body,
        visibility="public",
        source=source,
        document_id=document_id,
        status="active",
        index_zone="public",
        publication={
            "status": "published",
            "approved": True,
            "approved_by": approved_by,
            "approved_at": now,
            "public_version": 1,
        },
        event_type="onboarding.knowledge_published",
    )
