"""Tests for client alias fuzzy matching."""

from brain_platform.search.client_aliases import (
    expand_client_aliases,
    match_clients,
    normalize_compact,
)


def test_normalize_strips_hyphen_space():
    assert normalize_compact("Норд-Сервис СПб") == "нордсервисспб"
    assert normalize_compact("НордСервис-СПб") == "нордсервисспб"


def test_match_nordservice_variants():
    variants = [
        "НордСервис-СПб",
        "Норд-Сервис СПб",
        "Норд Сервис",
        "НордСервисСПб",
        "нордсервис",
        "Норд-сервис",
        "nord service спб",
        "нордсервес",
        "nordservis",
        "статус по Норд Сервису",
        "7816718222",
    ]
    for q in variants:
        hits = match_clients(q)
        assert hits, f"no match for {q!r}"
        assert hits[0].inn == "7816718222"


def test_expand_injects_canonical_and_inn():
    expanded = expand_client_aliases("Норд-сервис")
    low = " | ".join(expanded).lower()
    assert "7816718222" in low
    assert "нордсервис" in normalize_compact(" ".join(expanded))
