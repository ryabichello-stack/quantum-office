"""Heuristics for forcing the secretary to keep tool-calling until the task is solved."""

from __future__ import annotations

import re

_STALL_RE = re.compile(
    r"(хотите[, ]+чтобы я|укажите вариант|что предпочитаете|"
    r"поискал по\s*:|варианты поиска|запущу поиск|"
    r"могу (?:поискать|проверить|найти)|нужно уточн|"
    r"по\s*:\s*\n|какой вариант|"
    r"дополнительные данные|примерной дате)",
    re.I,
)


def looks_like_stall(text: str) -> bool:
    """True if the model stopped with a clarification menu instead of solving."""
    t = (text or "").strip()
    if len(t) < 8:
        return True
    if _STALL_RE.search(t):
        return True
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    bulletish = sum(1 for ln in lines if re.match(r"^([-•*]|\d+[.)])\s+", ln))
    if bulletish >= 2 and re.search(r"(поиск|email|инн|дат|переписк|вариант)", t, re.I):
        return True
    return False
