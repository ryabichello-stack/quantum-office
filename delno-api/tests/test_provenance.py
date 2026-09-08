"""E1.4 — unified knowledge provenance in delno-api responses."""

from app.services.provenance import (
    attach_sources_to_knowledge_response,
    extract_sources_from_knowledge,
    normalize_knowledge_match,
)


def test_normalize_knowledge_match_from_brain_hit():
    hit = {
        "document_id": "doc-1",
        "chunk_id": "chunk-9",
        "title": "Тарифы",
        "source": "demo/pricing.md",
        "citation": "demo/pricing.md#chunk-9",
        "snippet": "Диалоги — 2990 рублей в месяц",
        "provenance": {
            "tenant_id": "delno-demo",
            "source": "demo/pricing.md",
            "document_id": "doc-1",
            "chunk_id": "chunk-9",
        },
    }
    normalized = normalize_knowledge_match(hit)
    assert normalized["document_id"] == "doc-1"
    assert normalized["chunk_id"] == "chunk-9"
    assert normalized["source"] == "demo/pricing.md"
    assert "2990" in normalized["snippet_preview"]


def test_extract_sources_from_knowledge_payload():
    payload = {
        "ok": True,
        "matches": [
            {
                "document_id": "doc-1",
                "chunk_id": "c1",
                "title": "FAQ",
                "snippet": "Ответ",
            }
        ],
    }
    sources = extract_sources_from_knowledge(payload)
    assert len(sources) == 1
    assert sources[0]["title"] == "FAQ"


def test_attach_sources_to_knowledge_response():
    payload = {"ok": True, "matches": [{"document_id": "d", "title": "X", "snippet": "Y"}]}
    attach_sources_to_knowledge_response(payload)
    assert len(payload["sources"]) == 1
