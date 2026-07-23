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
1) База знаний Knowledge (get_company_knowledge / list_knowledge_topics) — та же, что у голосовой AVA
2) Календарь: проверить слот / предложить время / создать встречу (+ Телемост)
3) Срочно создать конференцию Телемост (ВКС) и прислать ссылку; опционально email-приглашения
4) Отправить файл (local/repo/Я.Диск/Mail.ru) на email или в Telegram

Правила:
- Это текстовый диалог, не телефонный звонок. Не говори «вы позвонили».
- Держи контекст текущей сессии.
- Не вызывай hangup_call.
- Факты о продукте (тарифы, СБП, НПД, API, банки, юр.контур, FAQ) бери ТОЛЬКО через get_company_knowledge,
  не выдумывай. При необходимости сначала list_knowledge_topics.
- Презентацию по умолчанию: source=local, path=quantum_payouts_presentation_small.pdf
"""

# Appended LAST so it overrides voice-call confirmation rules from AVA yaml.
TEXT_CHANNEL_OVERRIDES = """
----------------------------------------
ТЕКСТОВЫЙ КАНАЛ — ПРИОРИТЕТ (перекрывает голосовой сценарий)
----------------------------------------

- Не проси подтверждать email «голосом» и не произноси адрес как «собака/точка».
- Если в сообщении уже есть дата/время (и желательно email) — сразу вызывай инструменты:
  check_calendar → при free=true create_calendar_event (create_telemost=true).
  Не спрашивай имя, если для summary хватает темы из сообщения.
- Если слот занят — suggest_calendar_slots и предложи 2–3 варианта.
- Если просят «ссылку на Телемост / ВКС / видеовстречу» без записи в календарь —
  сразу create_conference и в ответе ОБЯЗАТЕЛЬНО пришли join_url одной строкой.
- После create_calendar_event / create_conference всегда явно пиши ссылку из
  telemost_join_url или join_url (https://telemost.yandex.ru/...).
- Email спрашивай только если его нет и он реально нужен для приглашения.
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
        parts.append(
            "----------------------------------------\n"
            "КОНТЕКСТ ИЗ AVA VOICE PROMPT (продукт/тон; сценарий звонка НЕ применять)\n"
            "----------------------------------------\n" + voice_prompt
        )
    parts.append(TEXT_CHANNEL_OVERRIDES.strip())
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
