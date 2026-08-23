"""Thematic macro-financial analysis for flywheel news."""

from __future__ import annotations

from modules.content_flywheel.thematic import (
    THEME_TAXONOMY,
    analyze_news_themes,
    build_thematic_brief,
    theme_min_score,
)


def test_high_relevance_payouts_news():
    out = analyze_news_themes(
        title="ЦБ поднял ключевую ставку",
        body="Ломбарды пересматривают массовые выплаты и оборот денежных потоков клиентам.",
    )
    assert out["theme_score"] >= theme_min_score()
    assert out["use_for_content"] is True
    assert "money_flows" in out["theme_tags"] or "mass_payouts" in out["theme_tags"]


def test_off_topic_news():
    out = analyze_news_themes(
        title="Новый сезон сериала",
        body="Премьера на стриминге в субботу.",
    )
    assert out["theme_tier"] == "off_topic"
    assert out["use_for_content"] is False


def test_build_thematic_brief_uses_hook():
    analysis = analyze_news_themes(
        title="СБП и выплаты",
        body="Банки ускоряют переводы для МФО.",
    )
    brief = build_thematic_brief(title="СБП и выплаты", body="...", analysis=analysis)
    assert "денеж" in brief.lower() or "выплат" in brief.lower() or "плат" in brief.lower()


def test_taxonomy_not_empty():
    assert "money_flows" in THEME_TAXONOMY
