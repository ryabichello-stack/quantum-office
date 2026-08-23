"""Macro-financial thematic analysis for flywheel news (money flows lens).

Primary lens: оборот денег, денежные потоки, платежи, ставки, регуляторика.
Product/company KB is an optional second layer (FLYWHEEL_USE_PRODUCT_KB).
"""

from __future__ import annotations

import os
import re
from typing import Any

# Theme ids → human labels (RU)
THEME_TAXONOMY: dict[str, str] = {
    "money_flows": "Денежные потоки и оборот",
    "mass_payouts": "Массовые выплаты",
    "payments_infra": "Платёжная инфраструктура",
    "banking_rates": "Ставки и стоимость денег",
    "lending": "Кредитование / ломбарды / МФО",
    "regulation": "Регуляторика и compliance",
    "macro": "Макроэкономика",
    "fintech": "Финтех и цифровизация",
}

# keyword → (theme_id, weight)
_KEYWORD_RULES: list[tuple[str, str, float]] = [
    (r"выплат", "mass_payouts", 1.2),
    (r"перевод", "money_flows", 1.0),
    (r"платеж|платёж|платежн", "payments_infra", 1.1),
    (r"оборот", "money_flows", 1.3),
    (r"денежн.{0,12}поток|cash.?flow", "money_flows", 1.4),
    (r"ликвидност", "money_flows", 1.1),
    (r"ключев.{0,6}ставк|ставк[аи].{0,8}цб|цб рф", "banking_rates", 1.3),
    (r"инфляц", "macro", 1.0),
    (r"макро", "macro", 0.9),
    (r"ломбард", "lending", 1.2),
    (r"\bмфо\b|микрофинанс|займ", "lending", 1.1),
    (r"кредит", "lending", 0.9),
    (r"регулятор|цб |115-?фз|комплаенс|kyc|aml", "regulation", 1.2),
    (r"эквайринг|сбп|fps|банк", "payments_infra", 0.85),
    (r"финтех|fintech|цифров.{0,8}плат", "fintech", 1.0),
    (r"интегратор|инфраструктур", "payments_infra", 0.8),
]


def theme_min_score() -> float:
    try:
        return float(os.getenv("FLYWHEEL_THEME_MIN_SCORE") or "0.35")
    except ValueError:
        return 0.35


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def analyze_news_themes(*, title: str, body: str) -> dict[str, Any]:
    """Score news against macro-financial / money-flow themes (rules-first)."""
    text = _normalize(f"{title}\n{body}")
    theme_scores: dict[str, float] = {tid: 0.0 for tid in THEME_TAXONOMY}
    matched: list[dict[str, Any]] = []

    for pattern, theme_id, weight in _KEYWORD_RULES:
        if re.search(pattern, text, flags=re.IGNORECASE):
            theme_scores[theme_id] = theme_scores.get(theme_id, 0) + weight
            matched.append({"pattern": pattern, "theme": theme_id, "weight": weight})

    # aggregate score 0..1 (cap at ~4 weighted hits)
    raw = sum(theme_scores.values())
    theme_score = min(1.0, round(raw / 4.0, 3))
    active_tags = [t for t, s in theme_scores.items() if s > 0]
    active_tags.sort(key=lambda t: theme_scores[t], reverse=True)

    if theme_score >= 0.65:
        tier = "high"
    elif theme_score >= theme_min_score():
        tier = "medium"
    elif theme_score >= 0.15:
        tier = "low"
    else:
        tier = "off_topic"

    primary = active_tags[0] if active_tags else None
    primary_label = THEME_TAXONOMY.get(primary or "", "Вне фокуса")

    hook = _build_editorial_hook(
        title=title,
        body=body,
        primary_theme=primary,
        primary_label=primary_label,
        tier=tier,
    )

    return {
        "theme_score": theme_score,
        "theme_tier": tier,
        "theme_tags": active_tags[:6],
        "theme_labels": [THEME_TAXONOMY.get(t, t) for t in active_tags[:6]],
        "primary_theme": primary,
        "primary_label": primary_label,
        "theme_scores": {k: v for k, v in theme_scores.items() if v > 0},
        "matched_keywords": matched[:12],
        "editorial_hook": hook,
        "lens": "macro_financial_money_flows",
        "use_for_content": tier in ("high", "medium"),
    }


def _build_editorial_hook(
    *,
    title: str,
    body: str,
    primary_theme: str | None,
    primary_label: str,
    tier: str,
) -> str:
    snippet = (body or title or "").strip()[:280]
    if tier == "off_topic":
        return (
            f"Новость вне ядра денежных потоков. Для мониторинга сохранено; "
            f"публикация не рекомендуется без ручной переформулировки."
        )
    prefix = {
        "money_flows": "С точки зрения оборота и денежных потоков",
        "mass_payouts": "Для рынка массовых выплат",
        "payments_infra": "С позиции платёжной инфраструктуры",
        "banking_rates": "В контексте стоимости денег и ставок",
        "lending": "Для ломбардов, МФО и кредитных ниш",
        "regulation": "С учётом регуляторики и compliance",
        "macro": "На макроуровне денежного рынка",
        "fintech": "В логике финтех- и цифровых платежей",
    }.get(primary_theme or "", "С точки зрения денежных потоков")

    return (
        f"{prefix}: {snippet}\n\n"
        f"Тема: {primary_label}. Релевантность для Quantum Labs (выплаты / инфраструктура): "
        f"{'высокая' if tier == 'high' else 'средняя'}."
    )


def build_thematic_brief(
    *,
    title: str,
    body: str,
    analysis: dict[str, Any],
    link: str = "",
) -> str:
    """Editorial brief: macro-financial angle first."""
    hook = (analysis.get("editorial_hook") or "").strip()
    parts = [hook]
    if title and title not in hook:
        parts.insert(0, f"**{title.strip()}**")
    brief = "\n\n".join(p for p in parts if p)
    if link and link not in brief:
        brief = f"{brief}\n\nИсточник: {link}"
    return brief[:4000]
