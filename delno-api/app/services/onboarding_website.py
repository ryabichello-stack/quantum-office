"""O4 — website URL ingestion inside onboarding conversation."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import upsert_draft_knowledge
from app.services.onboarding_summary import maybe_mark_summary_ready, register_onboarding_draft_document
from app.services.website_import import (
    build_knowledge_markdown,
    fetch_website_content,
    normalize_website_url,
)

URL_IN_TEXT_RE = re.compile(
    r"(https?://[^\s<>\"']+|www\.[^\s<>\"']+)",
    re.I,
)

DOMAIN_IN_TEXT_RE = re.compile(
    r"(?<![@\w])([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\."
    r"(?:ru|com|org|net|io|shop|store|biz|online|site|pro))(?:/[^\s<>\"']*)?",
    re.I,
)

GRACEFUL_FALLBACK = (
    "Я не смог забрать с сайта достаточно информации. "
    "Ничего страшного — можем собрать всё прямо здесь. "
    "Расскажите, чем вы занимаетесь, или загрузите материалы."
)


def extract_url_from_message(message: str) -> str | None:
    text = (message or "").strip()
    if not text:
        return None
    for pattern in (URL_IN_TEXT_RE, DOMAIN_IN_TEXT_RE):
        match = pattern.search(text)
        if match:
            candidate = match.group(1) if pattern is DOMAIN_IN_TEXT_RE else match.group(0)
            try:
                return normalize_website_url(candidate)
            except ValueError:
                continue
    return None


def _build_success_feedback(extracted: dict[str, Any]) -> str:
    url = str(extracted.get("url") or "")
    title = str(extracted.get("title") or "сайт")
    paragraphs = extracted.get("paragraphs") or []
    sections = extracted.get("sections") or []

    lines = [f"Посмотрел сайт {url}."]
    found: list[str] = []
    if extracted.get("description") or paragraphs:
        found.append("описание")
    if sections:
        found.append("разделы")
    if any("контакт" in str(s.get("heading", "")).lower() for s in sections):
        found.append("контакты")
    if any(re.search(r"\d{3,}", str(p)) for p in paragraphs[:8]):
        found.append("цифры/цены")

    if found:
        lines.append(f"Нашёл: {', '.join(found)}.")
    else:
        lines.append("На странице мало структурированной информации.")

    missing: list[str] = []
    blob = " ".join(str(p) for p in paragraphs[:10]).lower()
    if "график" not in blob and "час" not in blob and "режим" not in blob:
        missing.append("график работы")
    if not any("достав" in str(p).lower() for p in paragraphs[:10]):
        missing.append("условия доставки")

    if missing:
        lines.append(f"Не вижу: {', '.join(missing[:2])}. Подскажете?")
    elif len(paragraphs) < 3:
        lines.append("Если есть прайс — можете загрузить файл.")

    lines.append("Данные добавил в черновик.")
    return " ".join(lines)


def try_onboarding_url_ingest(
    db: Session,
    ctx: TenantContext,
    message: str,
) -> dict[str, Any] | None:
    """If message contains a URL, ingest to draft KB and return {reply, sources, tool_calls}."""
    url = extract_url_from_message(message)
    if not url:
        return None

    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="onboarding.website_added",
        category="operational",
        source="onboarding.website",
        payload={"url": url},
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="onboarding.website_import_started",
        category="operational",
        source="onboarding.website",
        payload={"url": url},
    )
    db.flush()

    try:
        extracted = fetch_website_content(url)
        markdown = str(extracted.get("markdown") or build_knowledge_markdown(extracted))
        title = str(extracted.get("title") or "Сайт компании")[:255]
        doc_id = f"doc-{tenant.slug}-web-{uuid.uuid4().hex[:10]}"

        kb = upsert_draft_knowledge(
            db,
            tenant,
            title=f"Сайт: {title}",
            body=markdown[:50000],
            source=f"onboarding.website:{url}",
            document_id=doc_id,
        )

        if not kb.get("ok"):
            raise ValueError("draft_upsert_failed")

        register_onboarding_draft_document(
            tenant,
            document_id=doc_id,
            title=f"Сайт: {title}",
            body=markdown[:50000],
            source_type="website",
            source_label=url,
            extra={"url": url},
        )
        maybe_mark_summary_ready(db, tenant)

        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.website_import_completed",
            category="operational",
            source="onboarding.website",
            payload={"url": url, "document_id": doc_id, "title": title[:120]},
        )
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.knowledge_draft_updated",
            category="operational",
            source="onboarding.website",
            payload={"document_id": doc_id, "url": url},
        )
        db.flush()

        reply = _build_success_feedback(extracted)
        return {
            "reply": reply,
            "tool_calls": [{"tool": "parse_website_source", "ok": True, "url": url}],
            "sources": [{"document_id": doc_id, "title": title, "source": url}],
        }
    except ValueError as exc:
        code = str(exc)
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.website_import_failed",
            category="operational",
            source="onboarding.website",
            payload={"url": url, "error": code},
        )
        db.flush()
        return {
            "reply": GRACEFUL_FALLBACK,
            "tool_calls": [{"tool": "parse_website_source", "ok": False, "url": url, "error": code}],
            "sources": [],
        }
    except Exception as exc:
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="onboarding.website_import_failed",
            category="operational",
            source="onboarding.website",
            payload={"url": url, "error": str(exc)[:200]},
        )
        db.flush()
        return {
            "reply": GRACEFUL_FALLBACK,
            "tool_calls": [{"tool": "parse_website_source", "ok": False, "url": url}],
            "sources": [],
        }
