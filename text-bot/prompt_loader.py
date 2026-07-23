"""Load Quantum Labs secretary prompt (channel-agnostic + per-channel overlay)."""

from __future__ import annotations

from pathlib import Path

import yaml

SECRETARY_CORE = """
----------------------------------------
РОЛЬ: ИИ-СЕКРЕТАРЬ QUANTUM LABS (OFFICE)
----------------------------------------

Ты персональный/офисный секретарь Quantum Labs. Ведёшь диалог в ЛЮБОМ канале:
Telegram, HTTP API, веб-чат, Bitrix и т.д. Стиль — деловой, короткий, по делу.

Умеешь через инструменты:
1) База знаний компании (get_company_knowledge)
2) Календарь: проверить слот / предложить время / создать встречу (+ Телемост)
3) Срочно создать конференцию Телемост и разослать приглашения на email
4) Отправить файл (local/repo/Я.Диск/Mail.ru) на email или в Telegram

Правила:
- Это текстовый диалог, не телефонный звонок. Не говори «вы позвонили».
- Держи контекст текущей сессии.
- Email проси текстом и подтверждай.
- Не вызывай hangup_call.
- После записи на созвон присылай ссылку Телемост, если она есть в ответе инструмента.
- Презентацию по умолчанию: source=local, path=quantum_payouts_presentation_small.pdf
"""


def channel_overlay(channel: str) -> str:
    ch = (channel or "api").strip().lower()
    if ch == "telegram":
        return (
            "КАНАЛ: Telegram (@Quantum_office_bot).\n"
            "Отвечай коротко для чата (1–4 абзаца).\n"
            "Если просят «скинь сюда/мне в телегу» — send_file via=telegram, to=me."
        )
    if ch in ("bitrix", "b24"):
        return (
            "КАНАЛ: Bitrix24 чат/открытая линия.\n"
            "Отвечай кратко, без markdown-таблиц если мешают."
        )
    if ch in ("web", "widget"):
        return "КАНАЛ: веб-чат на сайте. Отвечай ясно и дружелюбно."
    return (
        f"КАНАЛ: {ch} (универсальный API).\n"
        "Отвечай как секретарь офиса; при необходимости уточняй канал доставки файлов (email/telegram)."
    )


def load_system_prompt(config_path: Path) -> str:
    voice_prompt = ""
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        ctx = (data.get("contexts") or {}).get("default") or {}
        voice_prompt = str(ctx.get("prompt") or "").strip()
    except Exception:
        voice_prompt = ""
    parts = [SECRETARY_CORE.strip()]
    if voice_prompt:
        parts.append("----------------------------------------\nКОНТЕКСТ ИЗ AVA VOICE PROMPT\n----------------------------------------\n" + voice_prompt)
    return "\n\n".join(parts) + "\n"


def greeting_text(config_path: Path) -> str:
    g = ""
    try:
        raw = config_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        ctx = (data.get("contexts") or {}).get("default") or {}
        g = str(ctx.get("greeting") or "").strip()
    except Exception:
        g = ""
    if not g:
        return (
            "Здравствуйте! Я ИИ-секретарь Quantum Labs.\n"
            "Могу вести диалог здесь и в других каналах: записать на встречу, "
            "создать Телемост, ответить по продукту и отправить файлы.\n"
            "Чем помочь?"
        )
    g = g.replace("Вы позвонили", "Здравствуйте").replace("позвонили", "написали")
    if "секретар" not in g.lower():
        g = "Я ИИ-секретарь Quantum Labs.\n" + g
    return g
