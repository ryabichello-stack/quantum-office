"""Classify call outcome into a sheet note for «Пометки Клиента»."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any


INTEREST_RE = re.compile(
    r"(?i)(?:^|[^\w])(интересн\w*|давайте|перезвон\w*|свяжит\w*|встреч\w*|хочу\s+узнать|актуальн\w*|подходит)"
)
NEGATIVE_RE = re.compile(
    r"(?i)(?:^|[^\w])(не\s*интерес\w*|не\s*актуаль\w*|не\s*надо|отказа\w*|не\s*нужн\w*)"
)
NOANSWER_RE = re.compile(
    r"(?i)(?:^|[^\w])(автоответчик|голосовая\s+почта|не\s*бер\w*\s*труб\w*|недозвон|не\s*отвеча\w*|молчан\w*)"
)
CALLBACK_RE = re.compile(
    r"(?i)(?:^|[^\w])(перезвон\w*|позже|через\s+\d+|завтра|вечером)"
)


def _turns_text(conversation: list[Any] | str) -> str:
    if isinstance(conversation, str):
        return conversation
    parts: list[str] = []
    for t in conversation or []:
        if not isinstance(t, dict):
            continue
        role = str(t.get("role") or "")
        content = str(t.get("content") or t.get("text") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def classify_rules(conversation: list[Any] | str, *, outcome: str = "", duration: int = 0) -> dict[str, str]:
    text = _turns_text(conversation)
    low = text.lower()
    out = (outcome or "").lower()

    if duration and duration < 8 and not any(x in low for x in ("user:", "клиент")):
        return {
            "note": "НЕ ДОЗВОН",
            "status": "",
            "interest": "no",
            "method": "rules_short",
        }
    if NOANSWER_RE.search(text) or "no-answer" in out or "busy" in out:
        return {
            "note": "НЕ ДОЗВОН / автоответчик",
            "status": "",
            "interest": "no",
            "method": "rules_noanswer",
        }
    if INTEREST_RE.search(text) and not NEGATIVE_RE.search(text):
        note = "ИНТЕРЕСНО — перезвонить лично"
        if CALLBACK_RE.search(text):
            note = "ИНТЕРЕСНО — перезвонить лично (просил перезвонить)"
        return {
            "note": note,
            "status": "Положительный",
            "interest": "yes",
            "method": "rules_interest",
        }
    if NEGATIVE_RE.search(text):
        return {
            "note": "НЕ ИНТЕРЕСНО",
            "status": "",
            "interest": "no",
            "method": "rules_negative",
        }
    if CALLBACK_RE.search(text):
        return {
            "note": "ПЕРЕЗВОНИТЬ позже",
            "status": "",
            "interest": "maybe",
            "method": "rules_callback",
        }
    if not text.strip():
        return {
            "note": "НЕ ДОЗВОН",
            "status": "",
            "interest": "no",
            "method": "rules_empty",
        }
    return {
        "note": "СОСТОЯЛСЯ — уточнить итог",
        "status": "",
        "interest": "maybe",
        "method": "rules_unclear",
    }


def classify_llm(conversation: list[Any] | str, *, outcome: str = "", duration: int = 0) -> dict[str, str] | None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    model = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
    text = _turns_text(conversation)[:6000]
    prompt = (
        "По расшифровке исходящего звонка Quantum Labs про массовые выплаты "
        "верни JSON с полями note, status, interest.\n"
        "note — короткая пометка для колонки «Пометки Клиента» на русском, "
        "если интересно обязательно начни с «ИНТЕРЕСНО — перезвонить лично».\n"
        "status — «Положительный» если интерес есть, иначе пустая строка.\n"
        "interest — yes|no|maybe.\n"
        f"outcome={outcome} duration={duration}\n"
        f"transcript:\n{text}"
    )
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Ты классификатор итогов звонков. Отвечай только JSON."},
            {"role": "user", "content": prompt},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode())
        content = payload["choices"][0]["message"]["content"]
        data = json.loads(content)
        note = str(data.get("note") or "").strip() or "СОСТОЯЛСЯ — уточнить итог"
        return {
            "note": note,
            "status": str(data.get("status") or "").strip(),
            "interest": str(data.get("interest") or "maybe").strip().lower(),
            "method": "llm",
        }
    except Exception:
        return None


def classify(conversation: list[Any] | str, *, outcome: str = "", duration: int = 0) -> dict[str, str]:
    llm = classify_llm(conversation, outcome=outcome, duration=duration)
    if llm:
        return llm
    return classify_rules(conversation, outcome=outcome, duration=duration)
