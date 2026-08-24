"""Enrich Studio / Flywheel content with Second Brain + tenant product profile."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("ava-outreach.knowledge_enrich")

TENANTS_ROOT = Path(__file__).resolve().parent / "config" / "tenants"
DEFAULT_TENANT = "quantum-labs"

_PRODUCT_FALLBACK = [
    {"id": "quantum-labs", "name": "Quantum Labs"},
    {"id": "quantum-payouts", "name": "Quantum Payouts"},
]


def kb_enrich_enabled() -> bool:
    return (os.getenv("FLYWHEEL_KB_ENRICH") or os.getenv("CONTENT_USE_KB") or "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def load_tenant_products(tenant_id: str = DEFAULT_TENANT) -> list[dict[str, Any]]:
    path = TENANTS_ROOT / tenant_id / "product_profile.json"
    if not path.is_file():
        return list(_PRODUCT_FALLBACK)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        products = data.get("products") or []
        return products if products else list(_PRODUCT_FALLBACK)
    except (json.JSONDecodeError, OSError) as exc:
        logger.debug("product_profile read failed: %s", exc)
        return list(_PRODUCT_FALLBACK)


def _dedupe_citations(cites: list[dict[str, Any]], *, max_items: int = 5) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for c in cites:
        note = (c.get("note") or "").strip()
        key = note[:96].lower()
        if not note or key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= max_items:
            break
    return out


def build_search_queries(
    *,
    title: str,
    body: str,
    products: list[dict[str, Any]] | None = None,
) -> list[str]:
    products = products or load_tenant_products()
    queries: list[str] = []
    headline = (title or "").strip()
    snippet = (body or "").strip()[:200]
    if headline or snippet:
        queries.append(f"{headline} {snippet}".strip())
    queries.append("Quantum Labs платёжная инфраструктура ломбарды МФО выплаты")
    queries.append("Quantum Payouts массовые выплаты B2B продукт")
    for p in products[:3]:
        name = (p.get("name") or "").strip()
        if name:
            queries.append(f"{name} продукт возможности кейсы")
    # unique preserve order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        q = q.strip()
        if q and q not in seen:
            seen.add(q)
            unique.append(q)
    return unique


def fetch_product_context(
    *,
    title: str,
    body: str,
    tenant_id: str = DEFAULT_TENANT,
    limit: int = 5,
) -> dict[str, Any]:
    """Pull facts from ava-knowledge / Second Brain for content enrichment."""
    from knowledge_client import fetch_reply_citations, knowledge_base_url

    products = load_tenant_products(tenant_id)
    if not kb_enrich_enabled():
        return {
            "ok": True,
            "enabled": False,
            "citations": [],
            "products": products,
            "queries": [],
            "knowledge_base": knowledge_base_url(),
        }

    queries = build_search_queries(title=title, body=body, products=products)
    merged: list[dict[str, Any]] = []
    per_query = max(2, min(limit, 5))
    for q in queries[:4]:
        try:
            merged.extend(fetch_reply_citations(query=q, limit=per_query))
        except Exception as exc:  # noqa: BLE001
            logger.debug("kb fetch failed for %r: %s", q[:40], exc)

    citations = _dedupe_citations(merged, max_items=limit)
    return {
        "ok": True,
        "enabled": True,
        "citations": citations,
        "products": products,
        "queries": queries,
        "knowledge_base": knowledge_base_url(),
    }


def build_product_paragraph(
    citations: list[dict[str, Any]],
    *,
    products: list[dict[str, Any]] | None = None,
    max_len: int = 420,
) -> str:
    products = products or load_tenant_products()
    names = ", ".join((p.get("name") or "").strip() for p in products[:2] if p.get("name"))
    facts = [((c.get("note") or "").strip()) for c in citations if (c.get("note") or "").strip()]
    if not facts:
        return (
            f"{names or 'Quantum Labs'} — tech-партнёр по выплатам и платёжной инфраструктуре "
            f"для ломбардов и МФО (не посредник, прямые договоры с банками)."
        )[:max_len]

    parts: list[str] = []
    total = 0
    for fact in facts:
        chunk = fact if len(fact) <= 160 else fact[:157] + "…"
        if total + len(chunk) > max_len - 40:
            break
        parts.append(chunk)
        total += len(chunk)
    joined = " ".join(parts)
    prefix = f"Как {names}: " if names else "По нашей экспертизе: "
    return (prefix + joined)[:max_len]


def enrich_content_brief(
    *,
    title: str,
    body: str,
    link: str = "",
    tenant_id: str = DEFAULT_TENANT,
    limit: int = 5,
) -> dict[str, Any]:
    """Merge news/manual brief with KB product context for posts and video."""
    body = (body or "").strip()
    title = (title or "").strip()
    ctx = fetch_product_context(title=title, body=body, tenant_id=tenant_id, limit=limit)
    product_paragraph = build_product_paragraph(
        ctx.get("citations") or [],
        products=ctx.get("products"),
    )
    separator = "\n\n—\n\n"
    enriched = body
    if product_paragraph and product_paragraph not in body:
        enriched = f"{body}{separator}**Контекст:** {product_paragraph}"
    if link and link not in enriched:
        enriched = f"{enriched}\n\n{link}"

    return {
        **ctx,
        "title": title,
        "brief_original": body,
        "brief_enriched": enriched[:4000],
        "product_paragraph": product_paragraph,
        "approval_required": True,
    }


def citations_for_ui(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return ""
    lines = []
    for c in citations[:4]:
        ref = c.get("ref") or c.get("source") or "kb"
        note = (c.get("note") or "")[:120]
        lines.append(f"• [{ref}] {note}")
    return "\n".join(lines)
