"""P4 — Instant Demo: import website → tenant KB + widget-ready profile."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import upsert_tenant_knowledge_document
from app.services.website_import import build_knowledge_markdown, fetch_website_content, normalize_website_url


def _settings_dict(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings
    return dict(settings) if isinstance(settings, dict) else {}


def preview_website(url: str) -> dict[str, Any]:
    extracted = fetch_website_content(url)
    markdown = extracted.get("markdown") or build_knowledge_markdown(extracted)
    return {
        "ok": True,
        "url": extracted.get("url"),
        "title": extracted.get("title"),
        "description": extracted.get("description"),
        "paragraph_count": len(extracted.get("paragraphs") or []),
        "preview_excerpt": markdown[:1200],
        "sample_questions": _sample_questions(extracted),
    }


def _sample_questions(extracted: dict[str, Any]) -> list[str]:
    title = str(extracted.get("title") or "компании")
    return [
        f"Чем занимается {title}?",
        "Как с вами связаться?",
        "Какие услуги вы предлагаете?",
    ]


def import_website_to_tenant(
    db: Session,
    ctx: TenantContext,
    *,
    website_url: str,
    source: str = "tenant.instant_demo",
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    normalized = normalize_website_url(website_url)
    job_id = str(uuid4())

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="instant_demo.started",
        category="operational",
        source=source,
        payload={"job_id": job_id, "url": normalized},
    )

    extracted = fetch_website_content(normalized)
    title = str(extracted.get("title") or tenant.name).strip()[:255]
    body = str(extracted.get("markdown") or build_knowledge_markdown(extracted))

    kb_result = upsert_tenant_knowledge_document(
        db,
        tenant,
        title=f"{title} — сайт",
        body=body,
        visibility="public",
        source=source,
        document_id=f"doc-{tenant.slug}-website",
    )

    settings = _settings_dict(tenant)
    instant = {
        "job_id": job_id,
        "url": normalized,
        "title": title,
        "document_id": kb_result.get("document_id"),
        "kb_ok": kb_result.get("ok") is True,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }
    settings["instant_demo"] = instant
    # Count a successful website import as company knowledge for Hermes setup.
    hermes = dict(settings.get("hermes") or {})
    if kb_result.get("ok") is True:
        hermes["kb_ready"] = True
        hermes["company_profile_ready"] = True
        hermes["kb_source"] = source if source in (
            "hermes.import_website",
            "tenant.instant_demo",
            "website_import",
            "onboarding.website",
        ) else (source or "hermes.import_website")
        settings["hermes"] = hermes
    tenant.settings = settings

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="instant_demo.completed",
        category="operational",
        source=source,
        payload={
            "job_id": job_id,
            "url": normalized,
            "document_id": kb_result.get("document_id"),
            "kb_ok": kb_result.get("ok"),
        },
    )
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="ttfv.website_imported",
        category="operational",
        source=source,
        payload={"job_id": job_id},
    )

    paragraphs = [str(p).strip() for p in (extracted.get("paragraphs") or []) if str(p).strip()]
    sections = [
        str(s.get("heading") or "").strip()
        for s in (extracted.get("sections") or [])
        if isinstance(s, dict) and str(s.get("heading") or "").strip()
    ]
    kb_ok = kb_result.get("ok") is True
    return {
        "ok": kb_ok,
        "job_id": job_id,
        "url": normalized,
        "title": title,
        "description": str(extracted.get("description") or "")[:400],
        "document_id": kb_result.get("document_id"),
        "kb": kb_result,
        "kb_ok": kb_ok,
        "chars": len(body),
        "paragraph_count": len(paragraphs),
        "headings": sections[:8],
        "excerpt": "\n".join(paragraphs[:3])[:900],
        "site_key": tenant.public_key,
        "widget_embed": (
            f'<script src="https://cdn.dlno.ru/widget/v1/embed.js" '
            f'data-site-key="{tenant.public_key}" data-theme="auto" async></script>'
        ),
        "sample_questions": _sample_questions(extracted),
    }
