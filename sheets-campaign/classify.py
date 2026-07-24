"""Classify call outcome into a sheet note for «Пометки Клиента»."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from typing import Any


# «ИНТЕРЕСНО» — только если так высказался клиент (не AVA).
INTEREST_RE = re.compile(
    r"(?i)(?:^|[^\w])("
    r"интересн\w*"
    r"|актуальн\w*"
    r"|хочу\s+(?:узнать|послушать|разобрать|обсудить|подробн\w*)"
    r"|давайте\s+(?:обсуд\w*|созвон\w*|созвонимся|продолж\w*|запиш\w*|поговор\w*)"
    r"|готов\w*\s+(?:обсуд\w*|созвон\w*|встрет\w*|посмотр\w*)"
    r"|согласен\w*"
    r"|запишите?\s+меня"
    r"|можно\s+запис\w*"
    r")"
)
BOOKED_RE = re.compile(
    r"(?i)(?:^|[^\w])("
    r"встречу?\s+зафиксир"
    r"|приглашение\s+отправлен"
    r"|создал\w*\s+встреч"
    r"|записан\w*\s+на"
    r"|create_calendar_event"
    r"|telemost"
    r"|телемост"
    r")"
)
NEGATIVE_RE = re.compile(
    r"(?i)(?:^|[^\w])(не\s*интерес\w*|не\s*актуаль\w*|не\s*надо|отказа\w*|не\s*нужн\w*)"
)
NOANSWER_RE = re.compile(
    r"(?i)(?:^|[^\w])(автоответчик|голосовая\s+почта|не\s*бер\w*\s*труб\w*|недозвон|не\s*отвеча\w*|молчан\w*)"
)
CALLBACK_RE = re.compile(
    r"(?i)(?:^|[^\w])(перезвон\w*|свяжит\w*|позже|через\s+\d+|завтра|вечером)"
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


def client_expressed_interest(conversation: list[Any] | str) -> bool:
    user = _user_text(conversation)
    if not user.strip():
        return False
    if NEGATIVE_RE.search(user):
        return False
    return bool(INTEREST_RE.search(user))


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
    # Запись на консультацию — интерес подтверждён действием (календарь/Телемост).
    if BOOKED_RE.search(text):
        return {
            "note": "ИНТЕРЕСНО — записан на консультацию (календарь+Телемост+почта)",
            "status": "Положительный",
            "interest": "yes",
            "method": "rules_booked",
        }
    if client_expressed_interest(conversation):
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


def _sanitize_llm_result(
    data: dict[str, str],
    conversation: list[Any] | str,
) -> dict[str, str]:
    """Drop invented «ИНТЕРЕСНО» unless client said so or booking tools fired."""
    note = str(data.get("note") or "").strip() or "СОСТОЯЛСЯ — уточнить итог"
    interest = str(data.get("interest") or "maybe").strip().lower()
    status = str(data.get("status") or "").strip()
    text = _turns_text(conversation)
    booked = bool(BOOKED_RE.search(text))
    client_yes = client_expressed_interest(conversation)

    wants_interest = interest == "yes" or note.upper().startswith("ИНТЕРЕСНО")
    if wants_interest and not booked and not client_yes:
        fallback = classify_rules(conversation)
        fallback["method"] = "llm_sanitized_" + fallback["method"]
        return fallback

    if booked and not note.upper().startswith("ИНТЕРЕСНО"):
        note = "ИНТЕРЕСНО — записан на консультацию (календарь+Телемост+почта)"
        interest = "yes"
        status = "Положительный"

    return {
        "note": note,
        "status": status if interest == "yes" else "",
        "interest": interest,
        "method": "llm",
    }


def classify_llm(conversation: list[Any] | str, *, outcome: str = "", duration: int = 0) -> dict[str, str] | None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    model = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
    text = _turns_text(conversation)[:6000]
    user = _user_text(conversation)[:3000]
    prompt = (
        "По расшифровке исходящего звонка Quantum Labs про массовые выплаты "
        "верни JSON с полями note, status, interest.\n"
        "КРИТИЧНО: «ИНТЕРЕСНО» и interest=yes ставь ТОЛЬКО если клиент сам "
        "явно сказал об интересе (интересно/актуально/давайте обсудим/запишите меня) "
        "ИЛИ реально создана запись на консультацию (календарь/Телемост).\n"
        "Реплики ассистента (AVA) сами по себе НЕ считаются интересом.\n"
        "Короткие «да/алло/удобно» без интереса → не ИНТЕРЕСНО.\n"
        "note — короткая пометка для колонки «Пометки Клиента» на русском.\n"
        "Если запись на консультацию — note начинай с "
        "«ИНТЕРЕСНО — записан на консультацию».\n"
        "Если клиент явно заинтересован без записи — «ИНТЕРЕСНО — перезвонить лично».\n"
        "status — «Положительный» только при интересе/записи, иначе пустая строка.\n"
        "interest — yes|no|maybe.\n"
        f"outcome={outcome} duration={duration}\n"
        f"client_only:\n{user}\n"
        f"full_transcript:\n{text}"
    )
    body = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты классификатор итогов звонков. Отвечай только JSON. "
                    "ИНТЕРЕСНО только по словам клиента или факту записи."
                ),
            },
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
        return _sanitize_llm_result(
            {
                "note": str(data.get("note") or "").strip(),
                "status": str(data.get("status") or "").strip(),
                "interest": str(data.get("interest") or "maybe").strip().lower(),
            },
            conversation,
        )
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
