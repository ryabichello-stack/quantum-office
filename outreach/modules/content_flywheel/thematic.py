"""Thematic analysis — tenant-defined themes (universal, any niche)."""

from __future__ import annotations

import re
from typing import Any

from modules.content_flywheel.theme_config import (
    _keyword_matches,
    build_keyword_rules,
    load_theme_config,
    min_score_for_tenant,
    taxonomy_from_config,
)

DEFAULT_TENANT = "quantum-labs"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def analyze_news_themes(
    *,
    title: str,
    body: str,
    tenant_id: str = DEFAULT_TENANT,
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Score news against tenant-defined themes (keyword rules)."""
    cfg = config or load_theme_config(tenant_id)
    taxonomy = taxonomy_from_config(cfg)
    text = _normalize(f"{title}\n{body}")
    theme_scores: dict[str, float] = {tid: 0.0 for tid in taxonomy}
    matched: list[dict[str, Any]] = []

    for keyword, theme_id, weight in build_keyword_rules(cfg):
        if theme_id not in theme_scores:
            theme_scores[theme_id] = 0.0
        if _keyword_matches(text, keyword):
            theme_scores[theme_id] = theme_scores.get(theme_id, 0) + weight
            matched.append({"keyword": keyword, "theme": theme_id, "weight": weight})

    score_cap = float(cfg.get("score_cap") or 4.0)
    raw = sum(theme_scores.values())
    theme_score = min(1.0, round(raw / score_cap, 3))
    active_tags = [t for t, s in theme_scores.items() if s > 0]
    active_tags.sort(key=lambda t: theme_scores[t], reverse=True)

    min_score = float(cfg.get("min_score") or min_score_for_tenant(tenant_id))
    high_thr = float(cfg.get("high_tier_threshold") or 0.65)
    low_thr = float(cfg.get("low_tier_threshold") or 0.15)

    if theme_score >= high_thr:
        tier = "high"
    elif theme_score >= min_score:
        tier = "medium"
    elif theme_score >= low_thr:
        tier = "low"
    else:
        tier = "off_topic"

    primary = active_tags[0] if active_tags else None
    primary_label = taxonomy.get(primary or "", "Вне темы")
    theme_by_id = {t["id"]: t for t in cfg.get("themes") or []}

    hook = _build_editorial_hook(
        title=title,
        body=body,
        primary_theme=primary,
        primary_label=primary_label,
        tier=tier,
        config=cfg,
        theme_by_id=theme_by_id,
    )

    brand = (cfg.get("brand_short") or "").strip()
    relevance_note = brand or "вашей тематики"

    return {
        "theme_score": theme_score,
        "theme_tier": tier,
        "theme_tags": active_tags[:8],
        "theme_labels": [taxonomy.get(t, t) for t in active_tags[:8]],
        "primary_theme": primary,
        "primary_label": primary_label,
        "theme_scores": {k: v for k, v in theme_scores.items() if v > 0},
        "matched_keywords": matched[:16],
        "editorial_hook": hook,
        "lens": cfg.get("lens_id"),
        "lens_label": cfg.get("lens_label"),
        "min_score": min_score,
        "use_for_content": tier in ("high", "medium"),
        "relevance_note": relevance_note,
        "config_preset": cfg.get("preset"),
    }


def _build_editorial_hook(
    *,
    title: str,
    body: str,
    primary_theme: str | None,
    primary_label: str,
    tier: str,
    config: dict[str, Any],
    theme_by_id: dict[str, dict[str, Any]],
) -> str:
    snippet = (body or title or "").strip()[:280]
    if tier == "off_topic":
        return (config.get("off_topic_message") or "Новость вне заданной тематики.").strip()

    theme_row = theme_by_id.get(primary_theme or "") if primary_theme else None
    prefix = (
        (theme_row.get("hook_prefix") if theme_row else None)
        or config.get("default_hook_prefix")
        or "В контексте вашей темы"
    )
    brand = (config.get("brand_short") or "").strip()
    lens = (config.get("lens_label") or "").strip()
    rel = f"Релевантность ({lens or 'тема'}): {'высокая' if tier == 'high' else 'средняя'}."
    if brand:
        rel = f"Релевантность для {brand}: {'высокая' if tier == 'high' else 'средняя'}."

    return f"{prefix}: {snippet}\n\nТема: {primary_label}. {rel}"


def build_thematic_brief(
    *,
    title: str,
    body: str,
    analysis: dict[str, Any],
    link: str = "",
) -> str:
    hook = (analysis.get("editorial_hook") or "").strip()
    parts = [hook]
    if title and title not in hook:
        parts.insert(0, f"**{title.strip()}**")
    brief = "\n\n".join(p for p in parts if p)
    if link and link not in brief:
        brief = f"{brief}\n\nИсточник: {link}"
    return brief[:4000]
