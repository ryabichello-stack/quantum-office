"""Heuristics for forcing the secretary to keep tool-calling until the task is solved."""

from __future__ import annotations

import re

# Menus about *how/where* to search — force another tool step.
_SEARCH_MENU_RE = re.compile(
    r"(хотите[, ]+чтобы я|"
    r"укажите вариант|"
    r"что предпочитаете|"
    r"поискал по\s*:|"
    r"варианты поиска|"
    r"запущу поиск|"
    r"могу (?:поискать|проверить|найти)|"
    r"по\s*:\s*\n|"
    r"какой вариант|"
    r"как (?:искать|поискать)|"
    r"где искать|"
    r"примерной дате)",
    re.I,
)

# One concrete missing fact — allow returning to the user.
_LEGIT_CLARIFY_RE = re.compile(
    r"(уточни(?:те)?|"
    r"какой (?:инн|email|e-?mail|адрес|фио|период|дат|"
    r"компани|человек|контакт|тред|договор)|"
    r"какая (?:компани|дат|фамилия)|"
    r"какие (?:даты|фио)|"
    r"назови(?:те)? (?:инн|фио|email|компани)|"
    r"не хватает|"
    r"нужен (?:инн|email|фио|период)|"
    r"нужна (?:дат|фамилия|компани)|"
    r"нужно (?:имя|фио|уточнение)|"
    r"которую? из|"
    r"кого из|"
    r"имеешь в виду|"
    r"имеете в виду)",
    re.I,
)


def looks_like_legitimate_clarify(text: str) -> bool:
    """True if the reply asks for one concrete missing fact (not a search-method menu)."""
    t = (text or "").strip()
    if not t or _SEARCH_MENU_RE.search(t):
        return False
    if not _LEGIT_CLARIFY_RE.search(t):
        return False
    # Disallow multi-option search menus disguised as questions
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    bulletish = sum(1 for ln in lines if re.match(r"^([-•*]|\d+[.)])\s+", ln))
    if bulletish >= 2 and re.search(r"(поискать|поиск по|запущу|хотите)", t, re.I):
        return False
    return True


def looks_like_stall(text: str) -> bool:
    """True if the model stopped with a search-method menu instead of solving or clarifying."""
    t = (text or "").strip()
    if len(t) < 8:
        return True
    if looks_like_legitimate_clarify(t):
        return False
    if _SEARCH_MENU_RE.search(t):
        return True
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    bulletish = sum(1 for ln in lines if re.match(r"^([-•*]|\d+[.)])\s+", ln))
    if bulletish >= 2 and re.search(r"(поискать|поиск по|запущу|хотите|вариант)", t, re.I):
        return True
    return False
