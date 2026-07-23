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
BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "true").lower() not in ("0", "false", "no", "off")
BRAIN_TENANT_ID = os.getenv("BRAIN_TENANT_ID", "quantum-labs").strip() or "quantum-labs"

# Base tools available to everyone (guest + owner)
_KNOWLEDGE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_company_knowledge",
            "description": (
                "База знаний Quantum Labs / Quantum Payouts + Second Brain (FAQ). "
                "Обязательно вызывай по вопросам о продукте, СБП, тарифах, НПД, API/1С, "
                "банках, юр.контуре, FAQ. "
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
]

# Owner-only: full office memory (mail, contacts, threads, files)
_BRAIN_OWNER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_office_memory",
            "description": (
                "Second Brain: поиск по корпоративной памяти офиса — переписки (in/out), "
                "контакты, файлы на сервере, FAQ, темы проектов. "
                "Используй для рабочих вопросов: «кто писал про договор», «email клиента», "
                "«что обсуждали по ЕКОМ», любой офисный/технический контекст из почты и файлов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Свободный вопрос или ключевые слова",
                    },
                    "limit": {"type": "integer", "description": "Сколько фрагментов, по умолчанию 6"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_office_contact",
            "description": (
                "Найти контакт в Second Brain: email, телефон, должность, компания. "
                "По имени, email, телефону или компании."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Имя или свободный поиск"},
                    "email": {"type": "string"},
                    "phone": {"type": "string"},
                    "company": {"type": "string"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_office_threads",
            "description": (
                "Список тем переписки (email threads) из Second Brain. "
                "Поиск по subject/темам проектов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Фильтр по теме письма"},
                    "since": {
                        "type": "string",
                        "description": "ISO дата, с которой смотреть (опционально)",
                    },
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
]

_OFFICE_TOOLS: list[dict[str, Any]] = [
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


def tools_for_role(role: str) -> list[dict[str, Any]]:
    """Guests get FAQ knowledge; owners also get mail/contacts/threads memory tools."""
    tools = list(_KNOWLEDGE_TOOLS) + list(_OFFICE_TOOLS)
    if (role or "").strip().lower() == "owner" and BRAIN_ENABLED:
        tools = list(_KNOWLEDGE_TOOLS) + list(_BRAIN_OWNER_TOOLS) + list(_OFFICE_TOOLS)
    return tools


# Back-compat default (owner-capable set)
OPENAI_TOOLS: list[dict[str, Any]] = tools_for_role("owner")


def _headers(*, brain_principal: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if OFFICE_WEBHOOK_TOKEN:
        headers["X-Webhook-Token"] = OFFICE_WEBHOOK_TOKEN
    if brain_principal:
        headers["X-Principal-Id"] = brain_principal
        headers["X-Tenant-Id"] = BRAIN_TENANT_ID
    return headers


def _post_json(
    url: str,
    body: dict[str, Any],
    *,
    timeout: float = 20.0,
    brain_principal: str | None = None,
) -> dict[str, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST", headers=_headers(brain_principal=brain_principal)
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _get_json(url: str, *, timeout: float = 15.0, brain_principal: str | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        url, method="GET", headers=_headers(brain_principal=brain_principal)
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _brain_principal_for_role(role: str) -> str:
    if (role or "").strip().lower() == "owner":
        return "service:text-secretary"
    return "service:text-guest"


def _query_legacy_knowledge(knowledge: str, mailer: str, body: dict[str, Any]) -> dict[str, Any]:
    try:
        return _post_json(f"{knowledge}/api/knowledge/query", body)
    except Exception as exc:
        logger.warning("knowledge service failed (%s), fallback mailer", exc)
        return _post_json(f"{mailer}/api/knowledge/query", body)


def _query_brain_search(
    knowledge: str,
    query: str,
    *,
    principal: str,
    limit: int = 6,
    max_chars: int = 4500,
    faq_only: bool = False,
) -> dict[str, Any]:
    if not BRAIN_ENABLED or not query.strip():
        return {"ok": False, "text": "", "chars": 0, "matches": [], "skipped": True}
    try:
        data = _post_json(
            f"{knowledge}/api/brain/search",
            {"query": query, "limit": limit, "max_chars": max_chars},
            brain_principal=principal,
            timeout=25.0,
        )
    except Exception as exc:
        logger.warning("brain search failed: %s", exc)
        return {"ok": False, "error": str(exc), "text": "", "chars": 0, "matches": []}

    if faq_only and data.get("matches"):
        kept = [m for m in data["matches"] if (m.get("type") or "") in ("faq", "doc", "")]
        # If we filtered everything, keep original (assistant-safe principal already limits)
        if kept:
            # Rebuild text from kept titles only when possible — keep full text if mixed
            data = {**data, "matches": kept, "faq_filter": True}
    return data


def _merge_knowledge(legacy: dict[str, Any], brain: dict[str, Any]) -> dict[str, Any]:
    legacy_text = str(legacy.get("text") or "").strip()
    brain_text = str(brain.get("text") or "").strip()
    parts = []
    if legacy_text:
        parts.append(legacy_text)
    if brain_text and brain_text not in legacy_text:
        parts.append("— Second Brain —\n" + brain_text)
    text = "\n\n".join(parts)
    return {
        "ok": bool(legacy.get("ok") or brain.get("ok") or text),
        "topic": legacy.get("topic") or "",
        "topic_id": legacy.get("topic_id") or "",
        "text": text,
        "chars": len(text),
        "matches": legacy.get("matches") or [],
        "brain_matches": brain.get("matches") or [],
        "source": "legacy+brain" if brain_text else (legacy.get("source") or "legacy"),
    }


def run_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    mailer_base: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
    channel: Optional[str] = None,
    role: str = "guest",
) -> str:
    mailer = (mailer_base or MAILER_BASE).rstrip("/")
    knowledge = KNOWLEDGE_BASE.rstrip("/")
    principal = _brain_principal_for_role(role)
    is_owner = (role or "").strip().lower() == "owner"
    try:
        if name == "list_knowledge_topics":
            try:
                data = _get_json(f"{knowledge}/api/knowledge/topics")
            except Exception:
                data = {"ok": False, "topics": [], "error": "topics_unavailable"}
            return json.dumps(data, ensure_ascii=False)

        if name == "get_company_knowledge":
            topic = str(arguments.get("topic") or "").strip()
            topic_id = str(arguments.get("topic_id") or "").strip()
            body = {"topic": topic, "topic_id": topic_id}
            legacy = _query_legacy_knowledge(knowledge, mailer, body)
            brain_q = topic or topic_id
            brain = _query_brain_search(
                knowledge,
                brain_q,
                principal=principal,
                limit=6,
                faq_only=not is_owner,
            )
            return json.dumps(_merge_knowledge(legacy, brain), ensure_ascii=False)

        if name == "search_office_memory":
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Только для владельца"},
                    ensure_ascii=False,
                )
            query = str(arguments.get("query") or "").strip()
            limit = int(arguments.get("limit") or 6)
            data = _query_brain_search(
                knowledge,
                query,
                principal="service:text-secretary",
                limit=limit,
                max_chars=6000,
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "find_office_contact":
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Только для владельца"},
                    ensure_ascii=False,
                )
            data = _post_json(
                f"{knowledge}/api/brain/contacts/find",
                {
                    "q": str(arguments.get("q") or ""),
                    "email": str(arguments.get("email") or ""),
                    "phone": str(arguments.get("phone") or ""),
                    "company": str(arguments.get("company") or ""),
                    "limit": 20,
                },
                brain_principal="service:text-secretary",
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "list_office_threads":
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Только для владельца"},
                    ensure_ascii=False,
                )
            data = _post_json(
                f"{knowledge}/api/brain/threads/list",
                {
                    "q": str(arguments.get("q") or ""),
                    "since": arguments.get("since") or None,
                    "limit": int(arguments.get("limit") or 20),
                },
                brain_principal="service:text-secretary",
            )
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
