"""O5 — onboarding summary, conflicts, canonical profile, publish."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Message
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import publish_tenant_knowledge_document, upsert_draft_knowledge
from app.services.onboarding_flow import _merge_tenant_settings, get_onboarding_state
from app.services.onboarding_metrics import (
    MILESTONE_FIRST_EXTRACTION,
    MILESTONE_PUBLISHED,
    MILESTONE_STARTED,
    MILESTONE_SUMMARY_READY,
    record_ttfv_milestone,
)

PRICE_LINE_RE = re.compile(
    r"^[\s\-•*]*(.{2,50}?)\s+(\d[\d\s]{2,7})\s*(?:₽|руб\.?|RUB)?\s*$",
    re.I | re.M,
)
PHONE_RE = re.compile(r"(?:\+7|8)[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}")
EMAIL_RE = re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I)
HOURS_RE = re.compile(
    r"(пн|вт|ср|чт|пт|сб|вс)[^\n]{0,40}\d{1,2}[:\.]\d{2}",
    re.I,
)
ADDRESS_RE = re.compile(
    r"(?:ул\.|улица|пр\.|проспект|пер\.|бульвар|г\.)\s*[А-ЯA-Za-z0-9\s,\.-]{6,80}",
    re.I,
)

CONFIRM_PHRASES = (
    "всё верно",
    "все верно",
    "подтверждаю",
    "подтверждаем",
    "готово",
    "да, верно",
    "можно публиковать",
    "опублик",
)


def register_onboarding_draft_document(
    tenant: Tenant,
    *,
    document_id: str,
    title: str,
    body: str,
    source_type: str,
    source_label: str,
    extra: dict[str, Any] | None = None,
) -> None:
    state = get_onboarding_state(tenant)
    draft = dict(state.get("draft") or {})
    documents = dict(draft.get("documents") or {})
    documents[document_id] = {
        "title": title[:255],
        "body": body[:50000],
        "source_type": source_type,
        "source_label": source_label,
        **(extra or {}),
    }
    draft["documents"] = documents
    sources = list(draft.get("sources") or [])
    sources.append(
        {
            "type": source_type,
            "document_id": document_id,
            "label": source_label,
        }
    )
    # dedupe sources by document_id
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for item in reversed(sources):
        doc_id = str(item.get("document_id") or "")
        if doc_id and doc_id in seen:
            continue
        if doc_id:
            seen.add(doc_id)
        deduped.append(item)
    draft["sources"] = list(reversed(deduped))[-50:]
    _merge_tenant_settings(tenant, {"onboarding_draft": draft})


def register_onboarding_draft_document_with_metrics(
    db: Session,
    tenant: Tenant,
    *,
    tenant_id: UUID,
    document_id: str,
    title: str,
    body: str,
    source_type: str,
    source_label: str,
    extra: dict[str, Any] | None = None,
) -> None:
    register_onboarding_draft_document(
        tenant,
        document_id=document_id,
        title=title,
        body=body,
        source_type=source_type,
        source_label=source_label,
        extra=extra,
    )
    record_ttfv_milestone(
        db,
        tenant,
        MILESTONE_FIRST_EXTRACTION,
        tenant_id=tenant_id,
        extra={"source_type": source_type, "document_id": document_id},
    )


def _normalize_service_key(name: str) -> str:
    key = re.sub(r"[^\w\s]", " ", name.lower())
    key = re.sub(r"\s+", " ", key).strip()
    return key[:48] or "service"


def _combined_text(draft: dict[str, Any]) -> str:
    parts: list[str] = []
    for doc in (draft.get("documents") or {}).values():
        if isinstance(doc, dict):
            parts.append(str(doc.get("body") or ""))
    if draft.get("company_name"):
        parts.append(str(draft["company_name"]))
    if draft.get("notes"):
        parts.append(str(draft["notes"]))
    return "\n\n".join(parts)


def _extract_price_entries(text: str, source_label: str, source_type: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for match in PRICE_LINE_RE.finditer(text):
        label = match.group(1).strip(" -–|•")
        raw_price = re.sub(r"\s", "", match.group(2))
        try:
            price = int(raw_price)
        except ValueError:
            continue
        if price < 50 or price > 10_000_000:
            continue
        key = _normalize_service_key(label)
        entries.append(
            {
                "key": key,
                "label": label.strip(),
                "price": price,
                "source_type": source_type,
                "source_label": source_label,
            }
        )
    return entries


def detect_price_conflicts(draft: dict[str, Any]) -> list[dict[str, Any]]:
    by_key: dict[str, list[dict[str, Any]]] = {}
    for doc in (draft.get("documents") or {}).values():
        if not isinstance(doc, dict):
            continue
        body = str(doc.get("body") or "")
        source_label = str(doc.get("source_label") or doc.get("title") or "источник")
        source_type = str(doc.get("source_type") or "unknown")
        for entry in _extract_price_entries(body, source_label, source_type):
            by_key.setdefault(entry["key"], []).append(entry)

    conflicts: list[dict[str, Any]] = []
    canonical = draft.get("canonical") if isinstance(draft.get("canonical"), dict) else {}

    for key, items in by_key.items():
        prices = {item["price"] for item in items}
        if len(prices) <= 1:
            continue
        field = f"price.{key.replace(' ', '_')}"
        if field in canonical:
            continue
        conflicts.append(
            {
                "field": field,
                "label": items[0]["label"],
                "values": [
                    {
                        "price": item["price"],
                        "source_type": item["source_type"],
                        "source_label": item["source_label"],
                    }
                    for item in items
                ],
            }
        )
    return conflicts


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(0).strip() if match else None


def _extract_services(text: str, limit: int = 8) -> list[str]:
    services: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or len(line) < 4:
            continue
        if PRICE_LINE_RE.match(line):
            label = PRICE_LINE_RE.match(line).group(1).strip(" -–|•")  # type: ignore[union-attr]
            if label and label not in services:
                services.append(label[:80])
        elif line.startswith("## ") and len(line) > 4:
            heading = line[3:].strip()
            if heading.lower() not in ("текст со страницы", "источник"):
                services.append(heading[:80])
        if len(services) >= limit:
            break
    return services


def _extract_prices_summary(text: str, draft: dict[str, Any], limit: int = 6) -> list[str]:
    canonical = draft.get("canonical") if isinstance(draft.get("canonical"), dict) else {}
    lines: list[str] = []
    seen_keys: set[str] = set()

    for doc in (draft.get("documents") or {}).values():
        if not isinstance(doc, dict):
            continue
        body = str(doc.get("body") or "")
        source_label = str(doc.get("source_label") or "")
        for entry in _extract_price_entries(body, source_label, str(doc.get("source_type") or "")):
            field = f"price.{entry['key'].replace(' ', '_')}"
            if field in canonical:
                price = canonical[field]
                label = entry["label"]
            else:
                price = entry["price"]
                label = entry["label"]
            if entry["key"] in seen_keys:
                continue
            seen_keys.add(entry["key"])
            lines.append(f"{label} — {price} ₽")
            if len(lines) >= limit:
                return lines
    return lines


def _missing_fields(profile: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not profile.get("company_name"):
        missing.append("company_name")
    if not profile.get("services"):
        missing.append("services")
    if not profile.get("prices"):
        missing.append("prices")
    if not profile.get("address"):
        missing.append("address")
    if not profile.get("hours"):
        missing.append("hours")
    if not profile.get("contacts"):
        missing.append("contacts")
    return missing


def build_onboarding_summary(tenant: Tenant) -> dict[str, Any]:
    state = get_onboarding_state(tenant)
    draft = dict(state.get("draft") or {})
    text = _combined_text(draft)

    profile = {
        "company_name": draft.get("company_name") or tenant.name,
        "services": _extract_services(text),
        "prices": _extract_prices_summary(text, draft),
        "address": draft.get("address") or _first_match(ADDRESS_RE, text),
        "hours": draft.get("hours") or _first_match(HOURS_RE, text),
        "contacts": draft.get("contacts") or _format_contacts(text),
        "conditions": draft.get("conditions"),
        "faq": draft.get("faq") if isinstance(draft.get("faq"), list) else [],
    }

    conflicts = detect_price_conflicts(draft)
    missing = _missing_fields(profile)
    documents = draft.get("documents") or {}
    ready = bool(documents) and len(text.strip()) >= 80

    return {
        "ok": True,
        "status": state.get("status") or "in_progress",
        "summary_ready": ready or state.get("status") == "summary_ready",
        "profile": profile,
        "missing_fields": missing,
        "conflicts": conflicts,
        "document_ids": list(documents.keys()),
        "sources_count": len(documents),
    }


def _format_contacts(text: str) -> str | None:
    phones = PHONE_RE.findall(text)
    emails = EMAIL_RE.findall(text)
    parts: list[str] = []
    if phones:
        parts.append(phones[0])
    if emails:
        parts.append(emails[0])
    return ", ".join(parts) if parts else None


def maybe_mark_summary_ready(db: Session, tenant: Tenant) -> None:
    summary = build_onboarding_summary(tenant)
    state = get_onboarding_state(tenant)
    if state.get("status") == "published":
        return
    if summary["summary_ready"] and summary["document_ids"]:
        _merge_tenant_settings(
            tenant,
            {"onboarding": {"status": "summary_ready"}},
        )
        emit_event(
            db,
            tenant_id=tenant.id,
            event_type="onboarding.summary_ready",
            category="domain",
            source="onboarding.summary",
            payload={
                "document_ids": summary["document_ids"],
                "missing_fields": summary["missing_fields"],
                "conflicts_count": len(summary["conflicts"]),
            },
        )
        record_ttfv_milestone(
            db,
            tenant,
            MILESTONE_SUMMARY_READY,
            tenant_id=tenant.id,
            extra={"conflicts_count": len(summary["conflicts"])},
        )
        db.flush()


def resolve_onboarding_conflict(
    db: Session,
    tenant: Tenant,
    *,
    field: str,
    canonical_value: str | int,
) -> dict[str, Any]:
    state = get_onboarding_state(tenant)
    draft = dict(state.get("draft") or {})
    canonical = dict(draft.get("canonical") or {})
    canonical[field] = canonical_value
    draft["canonical"] = canonical
    conflicts = [c for c in detect_price_conflicts(draft) if c["field"] != field]
    draft["conflicts_resolved"] = list(set(list(draft.get("conflicts_resolved") or []) + [field]))
    _merge_tenant_settings(tenant, {"onboarding_draft": draft})
    maybe_mark_summary_ready(db, tenant)
    db.commit()
    return {"ok": True, "field": field, "canonical_value": canonical_value, "remaining_conflicts": conflicts}


def build_merged_publish_body(tenant: Tenant, summary: dict[str, Any]) -> str:
    profile = summary.get("profile") or {}
    lines = [
        f"# {profile.get('company_name') or tenant.name}",
        "",
        "## О компании",
        "",
    ]
    if profile.get("services"):
        lines.append("## Услуги")
        lines.append("")
        for svc in profile["services"]:
            lines.append(f"- {svc}")
        lines.append("")

    if profile.get("prices"):
        lines.append("## Цены")
        lines.append("")
        for price_line in profile["prices"]:
            lines.append(f"- {price_line}")
        lines.append("")

    for label, key in (
        ("Адрес", "address"),
        ("График", "hours"),
        ("Контакты", "contacts"),
        ("Условия", "conditions"),
    ):
        value = profile.get(key)
        if value:
            lines.extend([f"## {label}", "", str(value), ""])

    lines.append("## Источники")
    lines.append("")
    draft = get_onboarding_state(tenant).get("draft") or {}
    for doc in (draft.get("documents") or {}).values():
        if isinstance(doc, dict):
            lines.append(f"- {doc.get('source_type')}: {doc.get('source_label')}")

    body = "\n".join(lines).strip()
    return body if len(body) >= 40 else body + "\n\n(Профиль компании — DELNO onboarding.)"


def format_summary_message(summary: dict[str, Any]) -> str:
    profile = summary.get("profile") or {}
    lines = ["Вот что я понял о вашем бизнесе:", ""]

    def add_section(title: str, value: Any) -> None:
        if not value:
            return
        if isinstance(value, list):
            if not value:
                return
            lines.append(f"{title}:")
            for item in value[:8]:
                lines.append(f"  • {item}")
        else:
            lines.append(f"{title}: {value}")
        lines.append("")

    add_section("Компания", profile.get("company_name"))
    add_section("Услуги", profile.get("services"))
    add_section("Основные цены", profile.get("prices"))
    add_section("Адрес", profile.get("address"))
    add_section("График", profile.get("hours"))
    add_section("Контакты", profile.get("contacts"))
    add_section("Условия", profile.get("conditions"))

    missing = summary.get("missing_fields") or []
    if missing:
        labels = {
            "company_name": "название",
            "services": "услуги",
            "prices": "цены",
            "address": "адрес",
            "hours": "график",
            "contacts": "контакты",
        }
        lines.append("Не хватает: " + ", ".join(labels.get(m, m) for m in missing))
        lines.append("")

    conflicts = summary.get("conflicts") or []
    if conflicts:
        lines.append("Нужно уточнить цены:")
        for conflict in conflicts[:3]:
            vals = conflict.get("values") or []
            parts = [f"{v.get('source_label')}: {v.get('price')} ₽" for v in vals]
            lines.append(f"  • {conflict.get('label')}: {' vs '.join(parts)}")
        lines.append("")

    lines.append("Если всё верно — нажмите «Подтвердить» или напишите «Всё верно».")
    return "\n".join(lines).strip()


def publish_onboarding_from_summary(
    db: Session,
    ctx: TenantContext,
    *,
    approved_by: str,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    summary = build_onboarding_summary(tenant)

    if summary.get("conflicts"):
        return {"ok": False, "error": "unresolved_conflicts", "conflicts": summary["conflicts"]}

    if not summary.get("document_ids"):
        return {"ok": False, "error": "no_draft_documents"}

    merged_title = f"{tenant.name} — профиль для клиентов"
    merged_body = build_merged_publish_body(tenant, summary)
    merged_doc_id = f"doc-{tenant.slug}-onboarding-published"

    published: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    # Publish merged public profile for widget guests
    merged = publish_tenant_knowledge_document(
        db,
        tenant,
        document_id=merged_doc_id,
        title=merged_title,
        body=merged_body,
        approved_by=approved_by,
        source="onboarding.publish",
    )
    if merged.get("ok"):
        published.append({"document_id": merged_doc_id, **merged})
    else:
        errors.append({"document_id": merged_doc_id, **merged})

    # Publish individual source documents (canonical body preserved)
    for doc_id, doc in (get_onboarding_state(tenant).get("draft") or {}).get("documents", {}).items():
        if not isinstance(doc, dict):
            continue
        result = publish_tenant_knowledge_document(
            db,
            tenant,
            document_id=str(doc_id),
            title=str(doc.get("title") or "Документ"),
            body=str(doc.get("body") or ""),
            approved_by=approved_by,
            source="onboarding.publish",
        )
        if result.get("ok"):
            published.append({"document_id": doc_id, **result})
        else:
            errors.append({"document_id": doc_id, **result})

    if not published:
        db.commit()
        return {"ok": False, "published": published, "errors": errors}

    _merge_tenant_settings(
        tenant,
        {
            "onboarding": {
                "status": "published",
                "completed_at": _utc_now_iso(),
            },
        },
    )

    conversation_id = get_onboarding_state(tenant).get("conversation_id")
    if conversation_id:
        try:
            import uuid

            conv_uuid = uuid.UUID(str(conversation_id))
            db.add(
                Message(
                    tenant_id=ctx.tenant_id,
                    conversation_id=conv_uuid,
                    role="assistant",
                    body="Готово. Теперь я могу отвечать вашим клиентам.",
                    meta={"kind": "onboarding_published"},
                )
            )
        except ValueError:
            pass

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="onboarding.knowledge_confirmed",
        category="domain",
        source="onboarding.publish",
        payload={"approved_by": approved_by},
    )
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="onboarding.knowledge_published",
        category="domain",
        source="onboarding.publish",
        payload={"document_ids": [p["document_id"] for p in published], "count": len(published)},
    )
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="onboarding.completed",
        category="domain",
        source="onboarding.publish",
        payload={"document_ids": [p["document_id"] for p in published]},
    )
    record_ttfv_milestone(
        db,
        tenant,
        MILESTONE_PUBLISHED,
        tenant_id=tenant.id,
        extra={"document_ids": [p["document_id"] for p in published], "count": len(published)},
    )
    db.commit()

    return {
        "ok": not errors,
        "published": published,
        "errors": errors,
        "message": "Готово. Теперь я могу отвечать вашим клиентам.",
    }


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def is_confirm_message(message: str) -> bool:
    low = message.lower().strip()
    return any(phrase in low for phrase in CONFIRM_PHRASES)


def try_onboarding_summary_reply(db: Session, ctx: TenantContext, message: str) -> dict[str, Any] | None:
    """Handle summary request or confirm intent in onboarding chat."""
    low = message.lower().strip()
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    summary = build_onboarding_summary(tenant)

    if any(kw in low for kw in ("сводк", "что понял", "что ты понял", "покажи итог", "резюме")):
        maybe_mark_summary_ready(db, tenant)
        db.commit()
        return {"reply": format_summary_message(summary), "tool_calls": [{"tool": "inspect_onboarding_draft", "ok": True}]}

    if is_confirm_message(message):
        if summary.get("conflicts"):
            conflict = summary["conflicts"][0]
            vals = conflict.get("values") or []
            parts = [f"{v.get('source_label')}: {v.get('price')} ₽" for v in vals]
            return {
                "reply": (
                    f"Перед публикацией нужно уточнить: {conflict.get('label')} — "
                    f"{'; '.join(parts)}. Какая цена актуальна?"
                ),
                "tool_calls": [{"tool": "detect_knowledge_conflicts", "ok": True}],
            }
        if not summary.get("document_ids"):
            return {
                "reply": "Пока мало данных для публикации. Расскажите о бизнесе, дайте сайт или загрузите прайс.",
                "tool_calls": [],
            }
        result = publish_onboarding_from_summary(db, ctx, approved_by=f"user:{ctx.user_id or ctx.tenant_slug}")
        if result.get("ok"):
            return {"reply": result.get("message") or "Готово.", "tool_calls": [{"tool": "publish_onboarding_knowledge", "ok": True}]}
        return {
            "reply": "Не удалось опубликовать знания. Попробуйте ещё раз или уточните данные.",
            "tool_calls": [{"tool": "publish_onboarding_knowledge", "ok": False}],
        }

    # Price conflict resolution: "1800" or "актуальна 1800" after conflict question
    if re.search(r"\d{3,5}", message):
        draft = get_onboarding_state(tenant).get("draft") or {}
        conflicts = detect_price_conflicts(draft if isinstance(draft, dict) else {})
        if conflicts:
            price_match = re.search(r"(\d{3,5})", message.replace(" ", ""))
            if price_match:
                canonical = int(price_match.group(1))
                field = conflicts[0]["field"]
                resolve_onboarding_conflict(db, tenant, field=field, canonical_value=canonical)
                updated = build_onboarding_summary(tenant)
                return {
                    "reply": f"Принял: {conflicts[0]['label']} — {canonical} ₽.\n\n{format_summary_message(updated)}",
                    "tool_calls": [{"tool": "update_business_profile_draft", "ok": True}],
                }

    return None
