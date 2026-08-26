"""Sales training mode for outbound callers (PIN / allowlist).

Trainees get product Knowledge (FAQ-safe) only — no office mail, contacts,
Mail.ru disk browse, outbound dial, or campaign tools.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

ROLE_TRAINEE = "trainee"

_PIN_CMD_RE = re.compile(
    r"^\s*/?(?:обучение|train|training|учеба|учёба)\s+(.+?)\s*$",
    re.I,
)
_EXIT_WORDS = {
    "выход",
    "выкл",
    "off",
    "stop",
    "exit",
    "сброс",
    "clear",
    "logout",
    "выйти",
}


def training_enabled() -> bool:
    raw = (os.getenv("SECRETARY_TRAINING_ENABLED", "true") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def training_pin() -> str:
    return (os.getenv("SECRETARY_TRAINING_PIN", "") or "").strip()


def trainee_allowlist() -> set[str]:
    raw = (os.getenv("SECRETARY_TRAINEE_IDS", "") or "").strip()
    out: set[str] = set()
    for part in re.split(r"[\s,;]+", raw):
        if part.strip():
            out.add(part.strip())
    return out


def is_allowlisted_trainee(user_id: str) -> bool:
    uid = str(user_id or "").strip()
    return bool(uid) and uid in trainee_allowlist()


def pin_configured() -> bool:
    return bool(training_pin())


def verify_pin(candidate: str) -> bool:
    expected = training_pin()
    if not expected:
        return False
    got = (candidate or "").strip()
    # Digits-only PINs: ignore spaces/dashes employees may type
    if expected.isdigit():
        got = re.sub(r"[\s\-]+", "", got)
    return bool(got) and got == expected


def parse_training_command(text: str) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (action, payload).
    action: unlock | lock | help | None
    """
    raw = (text or "").strip()
    if not raw:
        return None, None
    low = raw.lower()
    if low in ("/обучение", "/train", "/training", "обучение", "train"):
        return "help", None
    m = _PIN_CMD_RE.match(raw)
    if not m:
        return None, None
    payload = (m.group(1) or "").strip()
    if payload.lower() in _EXIT_WORDS:
        return "lock", None
    if payload.lower() in ("help", "помощь", "?"):
        return "help", None
    return "unlock", payload


def training_help_text(*, unlocked: bool) -> str:
    lines = [
        "Режим обучения для сотрудников (обзвон / продажи Quantum Payouts).",
        "",
        "Доступ: только продуктовая база знаний (FAQ).",
        "Нет: внутренняя почта, контакты, диск Mail.ru, исходящие звонки бота.",
        "",
        "Команды:",
        "• /обучение <код> — включить",
        "• /обучение выход — выключить",
        "• /режимы — подрежимы обучения",
    ]
    if unlocked:
        lines.append("")
        lines.append("Сейчас режим обучения ВКЛЮЧЁН.")
    elif not pin_configured() and not trainee_allowlist():
        lines.append("")
        lines.append("Код ещё не задан на сервере (SECRETARY_TRAINING_PIN).")
    return "\n".join(lines)


def unlock_ok_text() -> str:
    return (
        "Ок, режим обучения включён.\n\n"
        "Я ваш тренер по продажам массовых выплат Quantum Labs.\n"
        "Помогу: разобрать продукт, ответить на вопросы клиента, написать скрипт "
        "холодного/тёплого звонка, отработать возражения, довести до приглашения на ВКС.\n\n"
        "Нет доступа к внутренней почте и файлам офиса — только Knowledge / FAQ.\n"
        "Выход: /обучение выход"
    )


def lock_ok_text() -> str:
    return "Режим обучения выключен. Снова обычный гостевой режим."


def wrong_pin_text() -> str:
    return "Неверный код. Формат: /обучение 123456"


def channels_allow_training(channel: str) -> bool:
    """Training unlock on consultant bots (Telegram + Max). Not on public client DMs."""
    ch = (channel or "").strip().lower()
    # Client-facing surfaces: always guest (no employee PIN unlock).
    if ch in {
        "whatsapp",
        "vk",
        "vkontakte",
        "web",
        "widget",
        "telegram_business",
        "bitrix",
        "b24",
    }:
        return False
    # telegram, max, api — one bot can be both hotline (guest) and training (PIN).
    return True
