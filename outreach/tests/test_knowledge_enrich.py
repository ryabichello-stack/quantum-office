"""Knowledge enrich for Studio content."""

from __future__ import annotations

from unittest.mock import patch

from knowledge_enrich import (
    build_product_paragraph,
    build_search_queries,
    enrich_content_brief,
    load_tenant_products,
)


def test_load_tenant_products():
    products = load_tenant_products("quantum-labs")
    assert any(p.get("id") == "quantum-payouts" for p in products)


def test_build_search_queries_includes_products():
    products = [{"name": "Quantum Payouts"}]
    qs = build_search_queries(title="Новость", body="рынок выплат", products=products)
    assert any("Quantum Payouts" in q for q in qs)


def test_enrich_content_brief_with_mock_kb():
    cites = [
        {"ref": "vault/lombards", "note": "Прямые договоры с банками для ломбардов", "source": "second_brain"},
    ]
    with patch("knowledge_enrich.fetch_product_context") as mock_fetch:
        mock_fetch.return_value = {
            "ok": True,
            "enabled": True,
            "citations": cites,
            "products": [{"name": "Quantum Labs"}],
            "queries": ["q1"],
        }
        out = enrich_content_brief(title="Тренд", body="Рынок ускоряется")
    assert "Контекст" in out["brief_enriched"]
    assert out["product_paragraph"]
    assert out["citations"]


def test_product_paragraph_fallback():
    p = build_product_paragraph([], products=[{"name": "Quantum Labs"}])
    assert "Quantum Labs" in p
