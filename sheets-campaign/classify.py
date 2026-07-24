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
BOOKED_RE = re.compile(
    r"(?i)(?:^|[^\w])(встречу?\s+зафиксир|приглашение\s+отправлен|создал\w*\s+встреч|записан\w*\s+на|create_calendar_event|telemost|телемост)"
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


def _turn_role(t: dict[str, Any]) -> str:
    role = str(t.get("role") or t.get("who") or "").strip().lower()
    if role in ("клиент", "client", "caller"):
        return "user"
    if role in ("ava", "assistant", "bot"):
        return "assistant"
    return role


def _turns_text(conversation: list[Any] | str) -> str:
    if isinstance(conversation, str):
        return conversation
    parts: list[str] = []
    for t in conversation or []:
        if not isinstance(t, dict):
            continue
        role = _turn_role(t) or str(t.get("role") or "")
        content = str(t.get("content") or t.get("text") or "").strip()
        if content:
            parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _user_text(conversation: list[Any] | str) -> str:
    """Only caller/ASR turns — never classify interest from AVA greeting/script."""
    if isinstance(conversation, str):
        # Legacy plain transcript: keep lines labeled user/клиент when present.
        lines = []
        for line in conversation.splitlines():
            low = line.strip().lower()
            if low.startswith(("user:", "клиент:", "client:", "caller:")):
                lines.append(line)
        return "\n".join(lines) if lines else ""
    parts: list[str] = []
    for t in conversation or []:
        if not isinstance(t, dict):
            continue
        if _turn_role(t) != "user":
            continue
        content = str(t.get("content") or t.get("text") or "").strip()
        if content:
            parts.append(content)
    return "\n".join(parts)


def has_user_speech(conversation: list[Any] | str) -> bool:
    return bool(_user_text(conversation).strip())


def classify_rules(conversation: list[Any] | str, *, outcome: str = "", duration: int = 0) -> dict[str, str]:
    text = _turns_text(conversation)
    user = _user_text(conversation)
    out = (outcome or "").lower()

    if not user.strip():
        if duration and duration < 20:
            return {
                "note": "НЕ ДОЗВОН",
                "status": "",
                "interest": "no",
                "method": "rules_no_user_short",
            }
        return {
            "note": "СОСТОЯЛСЯ — клиент не говорил / ASR пусто",
            "status": "",
            "interest": "maybe",
            "method": "rules_no_user",
        }
    if NOANSWER_RE.search(user) or NOANSWER_RE.search(text) or "no-answer" in out or "busy" in out:
        return {
            "note": "НЕ ДОЗВОН / автоответчик",
            "status": "",
            "interest": "no",
            "method": "rules_noanswer",
        }
    # Booking tools/phrases can be on the assistant side — keep full transcript.
    if BOOKED_RE.search(text):
        return {
            "note": "ИНТЕРЕСНО — записан на консультацию (календарь+Телемост+почта)",
            "status": "Положительный",
            "interest": "yes",
            "method": "rules_booked",
        }
    if INTEREST_RE.search(user) and not NEGATIVE_RE.search(user):
        note = "ИНТЕРЕСНО — перезвонить лично"
        if CALLBACK_RE.search(user):
            note = "ИНТЕРЕСНО — перезвонить лично (просил перезвонить)"
        return {
            "note": note,
            "status": "Положительный",
            "interest": "yes",
            "method": "rules_interest",
        }
    if NEGATIVE_RE.search(user):
        return {
            "note": "НЕ ИНТЕРЕСНО",
            "status": "",
            "interest": "no",
            "method": "rules_negative",
        }
    if CALLBACK_RE.search(user):
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
        "note — короткая пометка для колонки «Пометки Клиента» на русском.\n"
        "Если клиента записали на консультацию — note начинай с "
        "«ИНТЕРЕСНО — записан на консультацию».\n"
        "Если интересно, но без записи — «ИНТЕРЕСНО — перезвонить лично».\n"
        "status — «Положительный» если интерес/запись есть, иначе пустая строка.\n"
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
    # Without caller ASR, LLM often invents «ИНТЕРЕСНО» from AVA greeting alone.
    if not has_user_speech(conversation):
        return classify_rules(conversation, outcome=outcome, duration=duration)
    llm = classify_llm(conversation, outcome=outcome, duration=duration)
    if llm:
        return llm
    return classify_rules(conversation, outcome=outcome, duration=duration)
