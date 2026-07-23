"""Load Quantum Labs secretary prompt from AVA config."""

from __future__ import annotations

from pathlib import Path

import yaml

TEXT_CHANNEL_OVERLAY = """
----------------------------------------
КАНАЛ: TELEGRAM (ТЕКСТ) — Quantum Labs Office Bot
----------------------------------------

Ты ИИ-секретарь офиса Quantum Labs в Telegram.

Умеешь через инструменты:
1) База знаний компании (get_company_knowledge)
2) Календарь: проверить слот / предложить время / создать встречу (+ Телемост)
3) Срочно создать конференцию Телемост и разослать приглашения на email
4) Отправить файл (локальный/репозиторий/Я.Диск/Mail.ru) на email или в этот Telegram-чат

Правила канала:
- Пользователь пишет в Telegram, не звонит. Не говори «вы позвонили».
- Отвечай коротко (1–4 абзаца), удобно для чата.
- Email проси текстом и подтверждай.
- Не вызывай hangup_call.
- После записи на созвон присылай ссылку Телемост текстом, если она есть в ответе инструмента.
- Для «скинь мне файл сюда» используй send_file via=telegram, to=me (подставится текущий chat_id).
- Презентацию по умолчанию бери source=local, path=quantum_payouts_presentation_small.pdf
- Помни контекст переписки в этом чате.
"""


def load_system_prompt(config_path: Path) -> str:
    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    ctx = (data.get("contexts") or {}).get("default") or {}
    voice_prompt = str(ctx.get("prompt") or "").strip()
    if not voice_prompt:
        raise ValueError(f"empty prompt in {config_path}")
    return f"{voice_prompt.strip()}\n{TEXT_CHANNEL_OVERLAY.strip()}\n"


def greeting_text(config_path: Path) -> str:
    raw = config_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    ctx = (data.get("contexts") or {}).get("default") or {}
    g = str(ctx.get("greeting") or "").strip()
    if not g:
        return (
            "Здравствуйте! Я ИИ-секретарь Quantum Labs.\n"
            "Могу записать на встречу, создать Телемост, ответить по продукту "
            "и отправить файлы на почту или сюда в Telegram.\n"
            "Чем помочь?"
        )
    g = g.replace("Вы позвонили", "Вы написали").replace("позвонили", "написали")
    if "Телемост" not in g and "файл" not in g.lower():
        g += (
            "\n\nТакже могу срочно создать Телемост с приглашениями "
            "и отправить нужные файлы на почту или в этот чат."
        )
    return g
