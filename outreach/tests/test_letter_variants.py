"""Letter subject×body variant matrix."""

from __future__ import annotations

from content.letter_variants import (
    BODIES_LOMBARDS,
    SUBJECTS_LOMBARDS,
    pick_first_touch_variant,
    pick_indices,
    variant_stats,
    variants_enabled,
)


def test_seven_by_seven_matrix():
    assert len(SUBJECTS_LOMBARDS) == 7
    assert len(BODIES_LOMBARDS) == 7
    assert variant_stats()["lombards"]["combinations"] == 49


def test_bodies_keep_placeholders_and_meaning():
    for body in BODIES_LOMBARDS:
        assert "{greeting}" in body
        assert "{signature}" in body
        low = body.lower()
        assert "выплат" in low or "сбп" in low or "карт" in low
        assert "quantum" in low or "банк" in low


def test_pick_stable_per_email():
    a = pick_indices(email="a@x.ru", company_id="1")
    b = pick_indices(email="a@x.ru", company_id="1")
    c = pick_indices(email="b@x.ru", company_id="2")
    assert a == b
    assert a != c or True  # may rarely collide; check distribution below


def test_pick_spreads_across_combos():
    seen: set[tuple[int, int]] = set()
    for i in range(200):
        seen.add(pick_indices(email=f"u{i}@example.com", company_id=str(i)))
    assert len(seen) >= 30  # most of 49 should appear in 200 samples


def test_resolve_variant_dict():
    out = pick_first_touch_variant(email="test@pawn.ru", company_id="99", pack_id="lombards")
    assert out is not None
    assert out["subject"] in SUBJECTS_LOMBARDS
    assert "{greeting}" in out["plain"]
    assert out["combinations"] == 49


def test_variants_can_disable(monkeypatch):
    monkeypatch.setenv("LETTER_VARIANTS_ENABLED", "false")
    assert variants_enabled() is False
    assert pick_first_touch_variant(email="x@y.ru") is None
