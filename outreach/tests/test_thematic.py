"""Thematic analysis — tenant-defined themes."""

from __future__ import annotations

from modules.content_flywheel.theme_config import load_theme_config, min_score_for_tenant, taxonomy_from_config
from modules.content_flywheel.thematic import analyze_news_themes, build_thematic_brief

TENANT = "quantum-labs"


def test_high_relevance_payouts_news():
    out = analyze_news_themes(
        title="ЦБ поднял ключевую ставку",
        body="Ломбарды пересматривают массовые выплаты и оборот денежных потоков клиентам.",
        tenant_id=TENANT,
    )
    assert out["theme_score"] >= min_score_for_tenant(TENANT)
    assert out["use_for_content"] is True
    assert "money_flows" in out["theme_tags"] or "mass_payouts" in out["theme_tags"]


def test_off_topic_news():
    out = analyze_news_themes(
        title="Новый сезон сериала",
        body="Премьера на стриминге в субботу.",
        tenant_id=TENANT,
    )
    assert out["theme_tier"] == "off_topic"
    assert out["use_for_content"] is False


def test_build_thematic_brief_uses_hook():
    analysis = analyze_news_themes(
        title="СБП и выплаты",
        body="Банки ускоряют переводы для МФО.",
        tenant_id=TENANT,
    )
    brief = build_thematic_brief(title="СБП и выплаты", body="...", analysis=analysis)
    assert "денеж" in brief.lower() or "выплат" in brief.lower() or "плат" in brief.lower()


def test_taxonomy_from_tenant_config():
    cfg = load_theme_config(TENANT)
    tax = taxonomy_from_config(cfg)
    assert "money_flows" in tax


def test_custom_niche_config():
    cfg = {
        "lens_id": "real_estate",
        "lens_label": "Недвижимость",
        "min_score": 0.3,
        "themes": [
            {"id": "mortgage", "label": "Ипотека", "keywords": ["ипотек", "ставк"], "weight": 1.2},
            {"id": "rent", "label": "Аренда", "keywords": ["аренд", "съём"], "weight": 1.0},
        ],
    }
    out = analyze_news_themes(
        title="Банки снизили ставки по ипотеке",
        body="Спрос на новостройки вырос.",
        config=cfg,
    )
    assert out["use_for_content"] is True
    assert "mortgage" in out["theme_tags"]
