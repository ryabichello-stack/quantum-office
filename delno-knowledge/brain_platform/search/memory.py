"""Expand office-memory queries so one call covers related phrasings."""

from __future__ import annotations

import re

_SYNONYMS: dict[str, list[str]] = {
    "комплаенс": ["compliance", "комплаенс", "115-ФЗ", "kyс", "kyc", "aml"],
    "альф": ["альфа", "альфабанк", "альфа-банк", "alfabank", "alfa", "mv_mmb", "ypartsuf"],
    "alfa": ["alfabank", "alfa", "альфа", "mv_mmb"],
    "договор": ["договор", "соглашение", "contract", "подписан"],
    "интеграц": ["интеграция", "api", "подключ"],
    "сбп": ["сбп", "sbp"],
    "инн": ["инн", "inn", "огрн"],
}


def _tokens(q: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-zА-Яа-яЁё0-9_@.-]+", q or "") if len(t) >= 2]


def memory_query_variants(query: str) -> list[str]:
    q = re.sub(r"\s+", " ", (query or "").strip())
    if not q:
        return []

    low = q.lower()
    tokens = _tokens(low)

    priority: list[str] = [q]
    extras: list[str] = []

    has_comp = any(t.startswith("комплаен") or t in {"compliance", "kyc", "aml"} for t in tokens) or (
        "комплаен" in low
    )
    has_alfa = any(t.startswith("альф") or "alfa" in t for t in tokens) or ("альф" in low)

    # Domain expansions FIRST (most valuable)
    if has_comp:
        priority.extend(
            [
                "комплаенс",
                "compliance",
                "на комплаенс",
                "отправил на комплаенс",
                "115-ФЗ",
            ]
        )
    if has_alfa:
        priority.extend(
            [
                "alfabank",
                "Альфа-Банк",
                "mv_mmb",
                "mv_mmb@alfabank.ru",
                "ypartsuf",
                "ypartsuf@alfabank.ru",
            ]
        )
    if has_comp and has_alfa:
        priority = [
            q,
            "mv_mmb@alfabank.ru",
            "mv_mmb",
            "ypartsuf@alfabank.ru",
            "ООО ИНН",
            "на комплаенс",
            "отправил на комплаенс",
            "комплаенс alfabank",
            "комплаенс альфа",
            "alfabank",
            "комплаенс",
            "compliance",
        ] + priority[1:]

    # Stem synonyms
    for token in tokens:
        for stem, alts in _SYNONYMS.items():
            if token.startswith(stem) or stem.startswith(token[: max(3, len(stem))]):
                priority.extend(alts)

    # Tokens and emails last
    for t in tokens:
        if len(t) >= 4:
            extras.append(t)
        if "@" in t:
            extras.append(t)
            extras.append(t.split("@")[0])

    seen: set[str] = set()
    uniq: list[str] = []
    for v in priority + extras:
        v = v.strip()
        if len(v) < 2:
            continue
        key = v.lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(v)
    return uniq[:20]
