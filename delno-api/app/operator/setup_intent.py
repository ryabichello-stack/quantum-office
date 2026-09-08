"""Natural-language setup intents for cabinet Operator (live configuration)."""

from __future__ import annotations

import re
from typing import Any

_KB_PREFIXES = (
    "добавь в базу знаний",
    "добавь в kb",
    "запиши в базу знаний",
    "запиши в kb",
    "обнови базу знаний",
    "добавь в знания",
)

_SETTINGS_PREFIXES = (
    "измени настройки",
    "обнови настройки",
    "настрой ",
)

_SUMMARY_TRIGGERS = (
    "текущие настройки",
    "что настроено",
    "покажи настройки",
    "мой профиль",
    "сводка",
)

_FLAG_ALIASES: dict[str, str] = {
    "голос": "web_voice",
    "голосовой": "web_voice",
    "voice": "web_voice",
    "виджет": "web_voice",
    "чат": "web_voice",
    "telegram": "telegram",
    "телеграм": "telegram",
    "max": "max",
    "телефон": "phone",
    "звонки": "phone",
    "operator": "experimental_operator",
    "оператор": "experimental_operator",
}


def _split_title_body(text: str) -> tuple[str, str]:
    cleaned = text.strip()
    if not cleaned:
        return "Заметка", "—"
    for sep in (" — ", " – ", " - ", ": "):
        if sep in cleaned:
            left, right = cleaned.split(sep, 1)
            if left.strip() and right.strip():
                return left.strip()[:255], right.strip()
    if len(cleaned) <= 80:
        return cleaned[:255], cleaned
    dot = cleaned.find(". ")
    if 0 < dot < 80:
        return cleaned[: dot + 1].strip()[:255], cleaned
    return cleaned[:80].strip(), cleaned


def _parse_feature_flag(text: str) -> dict[str, Any] | None:
    lower = text.lower()
    enable = any(w in lower for w in ("включи", "enable", "активируй"))
    disable = any(w in lower for w in ("выключи", "disable", "отключи", "деактивируй"))
    if not enable and not disable:
        return None
    flag_key = None
    for alias, key in _FLAG_ALIASES.items():
        if alias in lower:
            flag_key = key
            break
    if not flag_key:
        return None
    return {
        "tool": "set_feature_flag",
        "params": {"flag_key": flag_key, "enabled": enable and not disable},
        "summary": f"{'Включить' if enable and not disable else 'Выключить'} «{flag_key}»",
    }


def _parse_hours(text: str) -> dict[str, Any] | None:
    lower = text.lower()
    if not any(w in lower for w in ("часы", "работаем", "график", "режим работы", "по субботам", "по будням")):
        return None
    body = text.strip()
    if len(body) < 8:
        return None
    title = "Часы работы"
    return {
        "tool": "upload_knowledge_snippet",
        "params": {"title": title, "body": body, "visibility": "public"},
        "summary": f"Добавить в KB: «{title}» — {body[:120]}",
    }


def _parse_settings_patch(text: str) -> dict[str, Any] | None:
    lower = text.lower()
    for prefix in _SETTINGS_PREFIXES:
        if lower.startswith(prefix):
            rest = text[len(prefix) :].strip(" :—-")
            if not rest:
                return None
            patch: dict[str, Any] = {}
            if "привет" in lower or " greeting" in lower:
                patch["greeting"] = rest
            elif "имя" in lower and "ассистент" in lower:
                patch["assistant_name"] = rest.split(":", 1)[-1].strip()[:120]
            else:
                patch["note"] = rest
            return {
                "tool": "update_tenant_settings",
                "params": {"patch": patch},
                "summary": f"Обновить настройки: {rest[:120]}",
            }
    name_match = re.search(r"имя\s+ассистента[:\s]+(.+)", lower)
    if name_match:
        name = text[name_match.start(1) :].strip()[:120]
        return {
            "tool": "update_tenant_settings",
            "params": {"patch": {"assistant_name": name}},
            "summary": f"Имя ассистента: {name}",
        }
    return None


def parse_setup_intent(message: str) -> dict[str, Any] | None:
    """Return {tool, params, summary} for cabinet setup commands, or None."""
    text = message.strip()
    if not text:
        return None
    lower = text.lower()

    for trigger in _SUMMARY_TRIGGERS:
        if trigger in lower:
            return {"tool": "get_tenant_summary", "params": {}, "summary": "Показать текущие настройки"}

    for prefix in _KB_PREFIXES:
        if lower.startswith(prefix):
            rest = text[len(prefix) :].strip(" :—-")
            title, body = _split_title_body(rest)
            if len(body) < 10:
                return None
            return {
                "tool": "upload_knowledge_snippet",
                "params": {"title": title, "body": body, "visibility": "public"},
                "summary": f"Добавить в KB: «{title}»",
            }

    flag = _parse_feature_flag(text)
    if flag:
        return flag

    hours = _parse_hours(text)
    if hours:
        return hours

    settings = _parse_settings_patch(text)
    if settings:
        return settings

    return None
