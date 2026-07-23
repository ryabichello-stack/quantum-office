"""Proxy tools to Quantum Labs office modules: mailer, calendar, conference, files."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").rstrip("/")
KNOWLEDGE_BASE = os.getenv("AVA_KNOWLEDGE_BASE", "http://127.0.0.1:8017").rstrip("/")
CALENDAR_BASE = os.getenv("AVA_CALENDAR_BASE", "http://127.0.0.1:8014").rstrip("/")
CONFERENCE_BASE = os.getenv("AVA_CONFERENCE_BASE", "http://127.0.0.1:8016").rstrip("/")
FILES_BASE = os.getenv("AVA_FILES_BASE", "http://127.0.0.1:8015").rstrip("/")
OFFICE_WEBHOOK_TOKEN = os.getenv("OFFICE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_company_knowledge",
            "description": (
                "База знаний Quantum Labs / Quantum Payouts (общая с голосовой AVA). "
                "Обязательно вызывай по вопросам о продукте, СБП, тарифах, НПД, API/1С, "
                "банках, юр.контуре, контактах, FAQ. "
                "topic — коротко на русском; topic_id — из list_knowledge_topics если известен."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Тема/вопрос коротко на русском"},
                    "topic_id": {
                        "type": "string",
                        "description": "id темы из list_knowledge_topics (tariffs, sbp, npd, ...)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_knowledge_topics",
            "description": (
                "Список тем базы знаний (id + названия + aliases). "
                "Вызови, если неясно, какой topic_id брать, или нужно сориентироваться по KB."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_calendar",
            "description": "Проверить, свободен ли слот. start: YYYY-MM-DD HH:MM (МСК).",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
                },
                "required": ["start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_calendar_slots",
            "description": "Предложить свободные слоты рядом с желаемым временем.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "YYYY-MM-DD HH:MM"},
                    "suggestions_count": {"type": "integer", "description": "Сколько вариантов, по умолчанию 3"},
                },
                "required": ["start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_calendar_event",
            "description": (
                "Создать событие в календаре Mail.ru (после check_calendar free=true). "
                "По умолчанию сразу создаёт Телемост/ВКС (create_telemost=true) и возвращает telemost_join_url."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "YYYY-MM-DD HH:MM МСК"},
                    "summary": {"type": "string", "description": "Тема встречи"},
                    "description": {"type": "string"},
                    "attendee_email": {"type": "string", "description": "Email участника, если есть"},
                    "create_telemost": {"type": "boolean"},
                    "send_telemost_invite": {"type": "boolean"},
                },
                "required": ["start", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_conference",
            "description": (
                "Создать Яндекс Телемост (ссылка на ВКС) по запросу. "
                "Используй, когда просят ссылку на видеовстречу/Телемост/ВКС без записи в календарь. "
                "В ответе будет join_url — его нужно прислать пользователю."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "invitees": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список email для приглашений (можно пустой)",
                    },
                    "when_text": {"type": "string", "description": "Когда, текстом, напр. сегодня 17:00 МСК"},
                    "message": {"type": "string", "description": "Комментарий в письме"},
                    "send_invites": {"type": "boolean"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": (
                "Отправить файл по email или в Telegram. "
                "source: local|repo|yadisk|mailru. via: email|telegram."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["local", "repo", "yadisk", "mailru"],
                    },
                    "path": {"type": "string", "description": "Путь к файлу в источнике"},
                    "via": {"type": "string", "enum": ["email", "telegram"]},
                    "to": {
                        "type": "string",
                        "description": "email или telegram chat_id",
                    },
                    "caption": {"type": "string"},
                    "subject": {"type": "string"},
                },
                "required": ["source", "path", "via", "to"],
            },
        },
    },
]


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if OFFICE_WEBHOOK_TOKEN:
        headers["X-Webhook-Token"] = OFFICE_WEBHOOK_TOKEN
    return headers


def _post_json(url: str, body: dict[str, Any], *, timeout: float = 20.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _get_json(url: str, *, timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(url, method="GET", headers=_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def run_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    mailer_base: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> str:
    mailer = (mailer_base or MAILER_BASE).rstrip("/")
    knowledge = KNOWLEDGE_BASE.rstrip("/")
    try:
        if name == "list_knowledge_topics":
            try:
                data = _get_json(f"{knowledge}/api/knowledge/topics")
            except Exception:
                # mailer may not expose topics; empty catalog is ok
                data = {"ok": False, "topics": [], "error": "topics_unavailable"}
            return json.dumps(data, ensure_ascii=False)

        if name == "get_company_knowledge":
            body = {
                "topic": str(arguments.get("topic") or ""),
                "topic_id": str(arguments.get("topic_id") or ""),
            }
            try:
                data = _post_json(f"{knowledge}/api/knowledge/query", body)
            except Exception as exc:
                logger.warning("knowledge service failed (%s), fallback mailer", exc)
                data = _post_json(f"{mailer}/api/knowledge/query", body)
            return json.dumps(data, ensure_ascii=False)

        if name == "check_calendar":
            data = _post_json(
                f"{CALENDAR_BASE}/api/calendar/check",
                {
                    "start": str(arguments.get("start") or ""),
                    "timezone": "Europe/Moscow",
                },
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "suggest_calendar_slots":
            data = _post_json(
                f"{CALENDAR_BASE}/api/calendar/suggest",
                {
                    "start": str(arguments.get("start") or ""),
                    "duration_min": 30,
                    "suggestions_count": int(arguments.get("suggestions_count") or 3),
                    "timezone": "Europe/Moscow",
                },
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "create_calendar_event":
            create_telemost = arguments.get("create_telemost")
            if create_telemost is None:
                create_telemost = True
            data = _post_json(
                f"{CALENDAR_BASE}/api/calendar/create",
                {
                    "start": str(arguments.get("start") or ""),
                    "summary": str(arguments.get("summary") or "Созвон с клиентом"),
                    "description": str(arguments.get("description") or ""),
                    "attendee_email": str(arguments.get("attendee_email") or ""),
                    "timezone": "Europe/Moscow",
                    "create_telemost": bool(create_telemost),
                    "send_telemost_invite": bool(arguments.get("send_telemost_invite") or False),
                },
                timeout=30.0,
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "create_conference":
            invitees = arguments.get("invitees") or []
            if isinstance(invitees, str):
                invitees = [x.strip() for x in invitees.split(",") if x.strip()]
            send_invites = arguments.get("send_invites")
            if send_invites is None:
                send_invites = bool(invitees)
            data = _post_json(
                f"{CONFERENCE_BASE}/api/conferences",
                {
                    "title": str(arguments.get("title") or "Встреча Quantum Labs"),
                    "invitees": list(invitees),
                    "when_text": str(arguments.get("when_text") or ""),
                    "message": str(arguments.get("message") or ""),
                    "send_invites": bool(send_invites),
                },
                timeout=30.0,
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "send_file":
            via = str(arguments.get("via") or "email").lower()
            to = str(arguments.get("to") or "").strip()
            if via in ("telegram", "tg") and (not to or to in ("me", "self", "этот чат")):
                to = str(telegram_chat_id or "")
            if via in ("telegram", "tg") and not to:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "telegram_chat_missing",
                        "message": "Нет telegram chat_id. Укажите to=chat_id или пишите из Telegram.",
                        "channel": channel,
                    },
                    ensure_ascii=False,
                )
            data = _post_json(
                f"{FILES_BASE}/api/files/send",
                {
                    "source": str(arguments.get("source") or "local"),
                    "path": str(arguments.get("path") or ""),
                    "via": via,
                    "to": to,
                    "caption": str(arguments.get("caption") or ""),
                    "subject": str(arguments.get("subject") or ""),
                },
                timeout=120.0,
            )
            return json.dumps(data, ensure_ascii=False)

        return json.dumps({"ok": False, "error": f"unknown tool: {name}"})
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("tool %s HTTP %s: %s", name, exc.code, err)
        return json.dumps({"ok": False, "error": err or str(exc)})
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return json.dumps({"ok": False, "error": str(exc)})
