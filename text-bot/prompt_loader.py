"""Load Quantum Labs secretary prompt from AVA config."""

from __future__ import annotations

from pathlib import Path

import yaml

TEXT_CHANNEL_OVERLAY = """
----------------------------------------
КАНАЛ: TELEGRAM (ТЕКСТ)
----------------------------------------

- Пользователь пишет в Telegram, не звонит. Не говори «вы позвонили» — говори «вы написали» / «спасибо за сообщение».
- Отвечай короткими сообщениями, удобными для чата (1–4 абзаца максимум).
- Email указывают текстом — попроси прислать и подтвердить; не нужно «озвучивать собака/точка».
- Не вызывай hangup_call — его нет в текстовом канале.
- Ссылку на Яндекс.Телемост можно отправить текстом после записи на созвон.
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
        return "Здравствуйте! Я ИИ-секретарь Quantum Labs. Чем могу помочь?"
    return g.replace("Вы позвонили", "Вы написали").replace("позвонили", "написали")
