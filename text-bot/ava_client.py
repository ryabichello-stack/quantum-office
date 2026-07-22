"""Proxy tools to ava-mailer (knowledge + calendar)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

OPENAI_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_company_knowledge",
            "description": (
                "База знаний Quantum Labs: услуги, СБП, тарифы, интеграция, контакты, сайт. "
                "topic — коротко на русском."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Тема вопроса коротко на русском"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_calendar",
            "description": "Проверить, свободен ли слот. start: YYYY-MM-DD HH:MM, timezone Europe/Moscow.",
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
            "name": "create_calendar_event",
            "description": (
                "Создать встречу после check_calendar (free=true). "
                "Нужны start, summary, description, attendee_email."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "summary": {"type": "string"},
                    "description": {"type": "string"},
                    "attendee_email": {"type": "string"},
                },
                "required": ["start", "summary", "description", "attendee_email"],
            },
        },
    },
]


def _post_json(url: str, body: dict[str, Any], *, timeout: float = 15.0) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def run_tool(name: str, arguments: dict[str, Any], *, mailer_base: str) -> str:
    try:
        if name == "get_company_knowledge":
            data = _post_json(
                f"{mailer_base.rstrip('/')}/api/knowledge/query",
                {"topic": str(arguments.get("topic") or "")},
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "check_calendar":
            data = _post_json(
                f"{mailer_base.rstrip('/')}/api/calendar/check",
                {
                    "start": str(arguments.get("start") or ""),
                    "timezone": "Europe/Moscow",
                },
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "create_calendar_event":
            data = _post_json(
                f"{mailer_base.rstrip('/')}/api/calendar/create",
                {
                    "start": str(arguments.get("start") or ""),
                    "summary": str(arguments.get("summary") or "Созвон с клиентом"),
                    "description": str(arguments.get("description") or ""),
                    "attendee_email": str(arguments.get("attendee_email") or ""),
                    "timezone": "Europe/Moscow",
                },
                timeout=20.0,
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
