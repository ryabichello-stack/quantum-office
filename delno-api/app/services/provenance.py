"""E1.4 — unified tenant-safe knowledge provenance in delno-api responses."""

from __future__ import annotations

from typing import Any


def normalize_knowledge_match(item: dict[str, Any]) -> dict[str, Any]:
    """Extract a stable, tenant-safe provenance record from a brain search hit."""
    prov = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    snippet = str(item.get("snippet") or item.get("text") or "").strip()
    record: dict[str, Any] = {
        "document_id": item.get("document_id") or prov.get("document_id"),
        "chunk_id": item.get("chunk_id") or prov.get("chunk_id"),
        "title": item.get("title"),
        "source": item.get("source") or prov.get("source"),
        "citation": item.get("citation"),
        "type": item.get("type"),
        "visibility": item.get("visibility"),
    }
    if snippet:
        record["snippet_preview"] = snippet[:240]
    if item.get("score") is not None:
        record["score"] = item.get("score")
    return {key: value for key, value in record.items() if value is not None}


def extract_sources_from_knowledge(data: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Return normalized sources list from a knowledge adapter/tool payload."""
    if not data or not data.get("ok", True):
        return []
    matches = data.get("matches") or data.get("results") or []
    sources: list[dict[str, Any]] = []
    for item in matches:
        if isinstance(item, dict):
            normalized = normalize_knowledge_match(item)
            if normalized.get("document_id") or normalized.get("title") or normalized.get("snippet_preview"):
                sources.append(normalized)
    return sources


def attach_sources_to_knowledge_response(data: dict[str, Any]) -> dict[str, Any]:
    """Mutate knowledge response with unified `sources` field (E1.4 contract)."""
    data["sources"] = extract_sources_from_knowledge(data)
    return data
