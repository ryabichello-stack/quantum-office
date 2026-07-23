"""Proxy tools to Quantum Labs office modules: mailer, calendar, conference, files, console."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").rstrip("/")
KNOWLEDGE_BASE = os.getenv("AVA_KNOWLEDGE_BASE", "http://127.0.0.1:8017").rstrip("/")
CALENDAR_BASE = os.getenv("AVA_CALENDAR_BASE", "http://127.0.0.1:8014").rstrip("/")
CONFERENCE_BASE = os.getenv("AVA_CONFERENCE_BASE", "http://127.0.0.1:8016").rstrip("/")
FILES_BASE = os.getenv("AVA_FILES_BASE", "http://127.0.0.1:8015").rstrip("/")
CONSOLE_BASE = os.getenv("AVA_CONSOLE_BASE", "http://127.0.0.1:8013").rstrip("/")
CONSOLE_TOKEN = os.getenv("CONSOLE_TOKEN", os.getenv("QUANTUM_CONSOLE_TOKEN", "")).strip()
OFFICE_WEBHOOK_TOKEN = os.getenv("OFFICE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()
BRAIN_ENABLED = os.getenv("BRAIN_ENABLED", "true").lower() not in ("0", "false", "no", "off")
BRAIN_TENANT_ID = os.getenv("BRAIN_TENANT_ID", "quantum-labs").strip() or "quantum-labs"
CONSOLE_ENABLED = os.getenv("CONSOLE_ENABLED", "true").lower() not in ("0", "false", "no", "off")

# Base tools available to everyone (guest + owner)
_KNOWLEDGE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_company_knowledge",
            "description": (
                "Факты о продукте/FAQ. Источник правды — Second Brain; "
                "legacy keyword MD только fallback. "
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
                "Second Brain: поиск по почте/файлам/FAQ/тредам. "
                "Вызывай СРАЗУ с вопросом пользователя как есть. "
                "Инструмент САМ расширяет запрос (синонимы, Альфа/alfabank/mv_mmb, "
                "комплаенс/compliance, отдельные слова) и ищет по всем вариантам. "
                "НЕ спрашивай пользователя «искать по email / ИНН / дате?» — просто вызови tool "
                "один раз и ответь фактами. Если пусто — скажи что не нашёл, без меню вариантов."
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
                "Найти человека в офисной памяти. Вызывай СРАЗУ с именем как сказал пользователь "
                "(например «Юля Парцуф») — инструмент САМ переберёт варианты написания "
                "(Юлия/Yuliya/Partsuf), email-local, переписки и треды. "
                "НЕ спрашивай пользователя, как искать — просто вызови этот tool один раз "
                "и по результату ответь фактами (email, телефон, компания, откуда нашли)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Имя или свободный поиск как сказал пользователь"},
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
    {
        "type": "function",
        "function": {
            "name": "expand_office_graph",
            "description": (
                "Граф Second Brain: кто с кем связан (человек↔компания↔треды). "
                "Вызывай после find_office_contact или когда нужно понять окружение "
                "контакта/компании (works_at, participant_of). "
                "Передай имя человека или компании как сказал пользователь."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "Имя человека или компании"},
                    "entity_id": {"type": "string", "description": "ID сущности из прошлого ответа"},
                    "depth": {"type": "integer", "description": "Глубина 1–2, по умолчанию 1"},
                    "limit": {"type": "integer"},
                },
                "required": [],
            },
        },
    },
]

# Owner-only: outbound dial + scenario via Quantum Console (never touches inbound default)
_OUTBOUND_OWNER_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "draft_outbound_call",
            "description": (
                "Собрать черновик исходящего звонка (greeting + script) по задаче. "
                "НЕ звонит. Вызывай СРАЗУ когда владелец просит позвонить. "
                "В ответе владельцу ОБЯЗАТЕЛЬНО вставь greeting и script целиком "
                "(нельзя писать «подтвердите черновик» без текста сценария)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Номер, если уже известен",
                    },
                    "goal": {
                        "type": "string",
                        "description": "Полная задача из сообщения владельца",
                    },
                    "greeting": {
                        "type": "string",
                        "description": "Опционально своя первая фраза (иначе соберём из goal)",
                    },
                    "script": {
                        "type": "string",
                        "description": "Опционально свой playbook (иначе соберём из goal)",
                    },
                    "callee_name": {
                        "type": "string",
                        "description": "Имя адресата, если известно (Света)",
                    },
                    "on_behalf_of": {
                        "type": "string",
                        "description": "От чьего имени звонить (Денис), если известно",
                    },
                },
                "required": ["goal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "outbound_dial",
            "description": (
                "Запустить ИСХОДЯЩИЙ звонок (Quantum Console → SIP/AVA). Только owner. "
                "Перед вызовом: 1) сам собери greeting+script по задаче (додумай пробелы), "
                "2) покажи черновик владельцу, 3) после «да, звони» вызови с confirm=true "
                "и теми же greeting+script (+ goal). "
                "Без goal/script звонок запрещён. use_knowledge обычно false."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Номер, напр. 79001234567 или +7 900 123-45-67",
                    },
                    "context": {
                        "type": "string",
                        "description": "AVA context профиля. Разрешено только outbound.",
                        "enum": ["outbound"],
                    },
                    "confirm": {
                        "type": "boolean",
                        "description": (
                            "true только после того как владелец увидел черновик "
                            "greeting/script и сказал «да, звони»"
                        ),
                    },
                    "goal": {
                        "type": "string",
                        "description": (
                            "Бриф задачи из чата (обязателен, если нет script). "
                            "Пример: «От имени Дениса пригласи Свету на свидание»"
                        ),
                    },
                    "greeting": {
                        "type": "string",
                        "description": (
                            "Первая фраза звонка из черновика, который показал владельцу"
                        ),
                    },
                    "script": {
                        "type": "string",
                        "description": (
                            "Полный playbook звонка из черновика (роль, цель, шаги, запреты)"
                        ),
                    },
                    "use_knowledge": {
                        "type": "boolean",
                        "description": (
                            "true — Second Brain; по умолчанию false для кастомного script/goal"
                        ),
                    },
                    "use_default_script": {
                        "type": "boolean",
                        "description": (
                            "true только если ЯВНО нужен постоянный YAML outbound shell. "
                            "Для разовых задач из чата не используй."
                        ),
                    },
                },
                "required": ["phone", "confirm"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_outbound_scenario",
            "description": (
                "Прочитать постоянный скрипт исходящих: greeting + script профиля outbound "
                "(изолирован от входящих). GET /api/outbound/script."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "enum": ["outbound"],
                        "description": "Только outbound",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_outbound_scenario",
            "description": (
                "Обновить ПОСТОЯННЫЙ скрипт исходящих (greeting и/или script). "
                "Входящий default НЕ меняется. PUT /api/outbound/script. "
                "Для one-shot звонка лучше передать script в outbound_dial."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "greeting": {"type": "string", "description": "Приветствие в начале звонка"},
                    "script": {
                        "type": "string",
                        "description": "Полный playbook / system prompt для исходящих",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "Синоним script (обратная совместимость)",
                    },
                    "use_knowledge": {
                        "type": "boolean",
                        "description": "Разрешить Second Brain в постоянном outbound-профиле",
                    },
                    "restart_engine": {
                        "type": "boolean",
                        "description": "Перезапустить ai_engine после сохранения (обычно не нужно)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_outbound_calls",
            "description": (
                "Список исходящих звонков из call_history (контекст outbound): "
                "номер, время, исход, превью расшифровки. "
                "НЕ используй сразу после dial для отчёта — бери await_outbound_result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Сколько записей, по умолчанию 15"},
                    "phone": {
                        "type": "string",
                        "description": "Фильтр по номеру (нормализуется)",
                    },
                    "context": {"type": "string", "enum": ["outbound", "default"]},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "await_outbound_result",
            "description": (
                "Дождаться ЗАВЕРШЕНИЯ исходящего звонка на номер и вернуть его расшифровку. "
                "Вызывай после outbound_dial вместо мгновенного list/get. "
                "Передай phone и dialed_after из ответа dial. "
                "Сводку владельцу строй ТОЛЬКО из conversation этого ответа — "
                "не выдумывай выплаты и не бери старые звонки."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {
                        "type": "string",
                        "description": "Номер, на который только что звонили",
                    },
                    "dialed_after": {
                        "type": "string",
                        "description": "ISO-время из ответа outbound_dial (dialed_at)",
                    },
                    "timeout_sec": {
                        "type": "integer",
                        "description": "Сколько ждать завершения, по умолчанию 180",
                    },
                },
                "required": ["phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_outbound_call",
            "description": (
                "Полная расшифровка одного звонка по call_id. "
                "Для отчёта сразу после dial предпочитай await_outbound_result."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "call_id": {"type": "string", "description": "id из list/await_outbound_*"},
                },
                "required": ["call_id"],
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
            "name": "browse_files",
            "description": (
                "Показать список папок и файлов (с датами) в Mail.ru / Я.Диск / local. "
                "Вызывай СРАЗУ при «покажи папки/диск/облако» — без допросов. "
                "По умолчанию source=mailru, path=/. "
                "Проваливайся в папку повторным вызовом с path. "
                "Для поиска по имени — search_files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "enum": ["mailru", "yadisk", "local"],
                        "description": "По умолчанию mailru",
                    },
                    "path": {
                        "type": "string",
                        "description": "Папка, по умолчанию / (корень)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_files",
            "description": (
                "Найти папки/файлы по имени (подстрока) в Mail.ru / Я.Диск / local. "
                "Вызывай СРАЗУ при «найди файл/папку …». Без допросов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Что искать, напр. презентация, договор, банк",
                    },
                    "source": {
                        "type": "string",
                        "enum": ["mailru", "yadisk", "local"],
                    },
                    "path": {
                        "type": "string",
                        "description": "Откуда искать, по умолчанию /",
                    },
                    "limit": {"type": "integer", "description": "Макс. результатов, по умолчанию 40"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_file",
            "description": (
                "Отправить файл по email или в Telegram. "
                "source: local|repo|yadisk|mailru. via: email|telegram. "
                "Путь бери из browse_files / search_files."
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
    """Guests get FAQ knowledge; owners also get mail/contacts + outbound console tools."""
    tools = list(_KNOWLEDGE_TOOLS) + list(_OFFICE_TOOLS)
    if (role or "").strip().lower() == "owner":
        owner_extra: list[dict[str, Any]] = []
        if BRAIN_ENABLED:
            owner_extra.extend(_BRAIN_OWNER_TOOLS)
        if CONSOLE_ENABLED and CONSOLE_BASE:
            owner_extra.extend(_OUTBOUND_OWNER_TOOLS)
        if owner_extra:
            tools = list(_KNOWLEDGE_TOOLS) + owner_extra + list(_OFFICE_TOOLS)
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


def _console_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if CONSOLE_TOKEN:
        # Console accepts either header; send both for compatibility.
        headers["X-Console-Token"] = CONSOLE_TOKEN
        headers["Authorization"] = f"Bearer {CONSOLE_TOKEN}"
    return headers


def _console_request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    if not CONSOLE_ENABLED:
        return {"ok": False, "error": "console_disabled"}
    if not CONSOLE_TOKEN:
        return {"ok": False, "error": "console_token_missing", "message": "Задайте CONSOLE_TOKEN"}
    qs = ""
    if query:
        qs = "?" + urllib.parse.urlencode({k: v for k, v in query.items() if v is not None})
    url = f"{CONSOLE_BASE}{path}{qs}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=_console_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {"ok": True}


def _normalize_dial_phone(raw: str) -> str:
    digits = re.sub(r"\D+", "", str(raw or ""))
    if digits.startswith("8") and len(digits) == 11:
        digits = "7" + digits[1:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "7" + digits
    return digits


_OUTBOUND_HANGUP_GUARD = (
    "КРИТИЧНО — НЕ РВИ ТРУБКУ РАНО:\n"
    "- ЗАПРЕЩЕНО вызывать hangup_call в первые 60 секунд и на первой реплике собеседника.\n"
    "- Обрывки ASR («авто», «сообщения», шум) НЕ считай автоответчиком — переспроси «Алло, меня слышно?».\n"
    "- hangup_call только при ясном отказе человека ИЛИ после короткого farewell на ЯВНЫЙ "
    "автоответчик («оставьте сообщение после сигнала»), не раньше.\n"
)

_DEFAULT_BRAND_RE = re.compile(
    r"(?i)\bquantum\s*labs\b|\bгари[кк]\b|\bмассовые\s+выплат\w*\b|\bсбп\b|"
    r"ии[‑\-]?секретар\w*\s+quantum|\bquantum\s*payouts\b"
)


def _goal_allows_default_brand(text: str) -> bool:
    return bool(_DEFAULT_BRAND_RE.search(text or ""))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_iso_ts(raw: str) -> float | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).timestamp()
    except Exception:
        return None


def _slim_call_conversation(call: dict[str, Any], call_id: str = "") -> dict[str, Any]:
    conv = call.get("conversation") or call.get("conversation_history") or []
    if isinstance(conv, str):
        try:
            conv = json.loads(conv)
        except Exception:
            conv = []
    slim_conv = []
    for turn in (conv or [])[:80]:
        if not isinstance(turn, dict):
            continue
        slim_conv.append(
            {
                "role": turn.get("role"),
                "content": (turn.get("content") or turn.get("text") or "")[:800],
            }
        )
    return {
        "ok": True,
        "call_id": call.get("call_id") or call_id,
        "caller_number": call.get("caller_number"),
        "context_name": call.get("context_name"),
        "start_time": call.get("start_time"),
        "duration_seconds": call.get("duration_seconds"),
        "outcome": call.get("outcome"),
        "total_turns": call.get("total_turns") or len(slim_conv),
        "conversation": slim_conv,
        "summary_rules": (
            "Сводку пиши ТОЛЬКО по полю conversation этого объекта. "
            "Не добавляй Quantum Labs / выплаты / старые звонки. "
            "Если собеседник согласился на день/время/место — скажи это явно."
        ),
    }


def _await_outbound_result(
    phone: str,
    *,
    dialed_after: str | None = None,
    timeout_sec: int = 180,
    poll_sec: float = 4.0,
) -> dict[str, Any]:
    phone_n = _normalize_dial_phone(phone)
    if not (phone_n.startswith("7") and len(phone_n) == 11):
        return {
            "ok": False,
            "error": "bad_phone",
            "message": "Нужен номер в формате 79XXXXXXXXX",
            "normalized": phone_n,
        }
    after_ts = _parse_iso_ts(dialed_after or "")
    # Small skew: accept calls starting a few seconds before dialed_at
    if after_ts is not None:
        after_ts -= 15
    timeout_sec = max(15, min(int(timeout_sec or 180), 300))
    deadline = time.time() + timeout_sec
    last_seen: dict[str, Any] | None = None

    while time.time() < deadline:
        listing = _console_request(
            "GET",
            "/api/calls",
            query={"limit": 30, "context": "outbound"},
        )
        for c in listing.get("calls") or []:
            if not isinstance(c, dict):
                continue
            num = _normalize_dial_phone(str(c.get("caller_number") or ""))
            if num != phone_n:
                continue
            start_ts = _parse_iso_ts(str(c.get("start_time") or ""))
            if after_ts is not None and start_ts is not None and start_ts < after_ts:
                continue
            last_seen = c
            dur = float(c.get("duration_seconds") or 0)
            outcome = str(c.get("outcome") or "").lower()
            preview = str(c.get("transcript_preview") or "")
            finished = outcome in {
                "completed",
                "abandoned",
                "failed",
                "no_answer",
                "busy",
                "agent_hangup",
                "caller_hangup",
            } or dur >= 8
            has_speech = bool(preview and preview not in ("[]", "null"))
            if not (finished and (has_speech or dur >= 3)):
                continue
            call_id = str(c.get("call_id") or "").strip()
            if not call_id:
                continue
            detail = _console_request(
                "GET",
                f"/api/calls/{urllib.parse.quote(call_id, safe='')}",
            )
            call = detail.get("call") if isinstance(detail, dict) else None
            if not isinstance(call, dict):
                continue
            slim = _slim_call_conversation(call, call_id=call_id)
            # Prefer calls that already have user/assistant turns
            if slim.get("conversation") or dur >= 8:
                slim["waited_sec"] = round(timeout_sec - max(0.0, deadline - time.time()), 1)
                slim["matched_phone"] = phone_n
                return slim
        time.sleep(poll_sec)

    return {
        "ok": False,
        "error": "timeout",
        "message": (
            "Звонок ещё не завершён или не появился в call_history. "
            "Подожди и вызови await_outbound_result снова — не суммируй старые звонки."
        ),
        "phone": phone_n,
        "dialed_after": dialed_after,
        "last_seen": {
            "call_id": (last_seen or {}).get("call_id"),
            "start_time": (last_seen or {}).get("start_time"),
            "duration_seconds": (last_seen or {}).get("duration_seconds"),
            "outcome": (last_seen or {}).get("outcome"),
        }
        if last_seen
        else None,
    }


def _scrub_default_brand_text(text: str) -> str:
    """Remove leaked office brand from a draft line when the task didn't ask for it."""
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    cleaned = re.sub(
        r"(?i)\s*,?\s*это\s+ии[‑\-]?секретар\w*\s+quantum\s*labs\s*,?",
        ", ",
        cleaned,
    )
    cleaned = re.sub(r"(?i)\bии[‑\-]?секретар\w*\s+quantum\s*labs\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bquantum\s*labs\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bгари[кк]\b", "", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+,", ",", cleaned)
    cleaned = cleaned.strip(" ,;—-")
    return cleaned


def _scrub_outbound_brand_leak(
    *,
    goal: str,
    greeting: str | None,
    script: str | None,
) -> tuple[str | None, str | None, bool]:
    """If task isn't about Quantum/payouts, strip brand leaks from draft fields."""
    if _goal_allows_default_brand(goal):
        return greeting, script, False

    scrubbed = False
    greet = greeting
    body = script
    if greet and _DEFAULT_BRAND_RE.search(greet):
        greet = _scrub_default_brand_text(greet) or "Здравствуйте! Удобно пару секунд?"
        scrubbed = True
    if body and _DEFAULT_BRAND_RE.search(body):
        body = (
            "ЗАПРЕТ ИДЕНТИЧНОСТИ: не упоминай Quantum Labs, Гарика, массовые выплаты, СБП.\n"
            "Говори только по задаче владельца.\n\n"
            + body
        )
        scrubbed = True
    return greet, body, scrubbed


def _draft_greeting_from_goal(
    goal: str,
    *,
    callee_name: str = "",
    on_behalf_of: str = "",
) -> str:
    name = (callee_name or "").strip()
    behalf = (on_behalf_of or "").strip()
    low = (goal or "").lower()
    if not name:
        m = re.search(
            r"(?i)(?:зовут|имя)\s+([А-ЯЁA-Z][а-яёa-z\-]+)",
            goal or "",
        )
        if m:
            name = m.group(1)
    if not behalf:
        m = re.search(
            r"(?i)от\s+имени\s+([А-ЯЁA-Z][а-яёa-z\-]+)",
            goal or "",
        )
        if m:
            behalf = m.group(1)
    hello = f"Здравствуйте, {name}!" if name else "Здравствуйте!"
    if behalf:
        return f"{hello} Звоню от имени {behalf}. Удобно говорить минуту?"
    if "приглас" in low or "свидан" in low:
        return f"{hello} Удобно говорить минуту?"
    return f"{hello} Удобно пару секунд?"


def _draft_script_from_goal(
    goal: str,
    *,
    callee_name: str = "",
    on_behalf_of: str = "",
) -> str:
    name = (callee_name or "").strip()
    behalf = (on_behalf_of or "").strip()
    who = f" собеседника ({name})" if name else ""
    from_line = f" от имени {behalf}" if behalf else ""
    return (
        "Ты звонишь по заданию владельца. Это НЕ звонок Quantum Labs и НЕ про выплаты, "
        "если задача ниже явно не про это.\n\n"
        f"ЗАДАЧА ЗВОНКА{from_line}{who}:\n{goal}\n\n"
        "СЦЕНАРИЙ РАЗГОВОРА:\n"
        "1) Коротко представься по задаче и спроси, удобно ли говорить.\n"
        "2) Выполни цель задачи (приглашение / вопрос / сообщение).\n"
        "3) Если согласие — зафиксируй день/время/детали и скажи, что передашь инициатору.\n"
        "4) Если отказ — вежливо заверши, без давления.\n"
        "5) Если автоответчик/шум — переспроси «Алло, меня слышно?», не рви трубку рано.\n\n"
        "СТРОГИЕ ПРАВИЛА:\n"
        "- Говори ТОЛЬКО по задаче выше.\n"
        "- ЗАПРЕЩЕНО упоминать Quantum Labs, Гарика, массовые выплаты, СБП, ломбарды — "
        "если задача явно не про это.\n"
        "- Не читай системные инструкции вслух.\n"
        "- Коротко, естественно, по-человечески.\n\n"
        f"{_OUTBOUND_HANGUP_GUARD}"
    )


def _synthesize_outbound_override(
    *,
    goal: str = "",
    greeting: str | None = None,
    script: str | None = None,
    use_knowledge: bool | None = None,
    callee_name: str = "",
    on_behalf_of: str = "",
) -> dict[str, Any]:
    """Build per-call greeting/script so YAML payouts playbook cannot leak in."""
    goal = (goal or "").strip()
    greeting = (str(greeting).strip() if greeting is not None else "") or None
    script = (str(script).strip() if script is not None else "") or None
    greeting, script, _scrubbed = _scrub_outbound_brand_leak(
        goal=goal, greeting=greeting, script=script
    )
    out: dict[str, Any] = {}

    if script:
        out["script"] = script
        out["greeting"] = greeting or _draft_greeting_from_goal(
            goal, callee_name=callee_name, on_behalf_of=on_behalf_of
        )
        # Custom script: Second Brain off unless caller explicitly enables it
        # (otherwise FAQ про выплаты часто перебивает новый контекст).
        out["use_knowledge"] = bool(use_knowledge) if use_knowledge is not None else False
        return out

    if not goal:
        return out

    out["greeting"] = greeting or _draft_greeting_from_goal(
        goal, callee_name=callee_name, on_behalf_of=on_behalf_of
    )
    out["script"] = _draft_script_from_goal(
        goal, callee_name=callee_name, on_behalf_of=on_behalf_of
    )
    out["use_knowledge"] = bool(use_knowledge) if use_knowledge is not None else False
    return out


def _format_draft_for_owner(draft: dict[str, Any]) -> str:
    phone = draft.get("phone") or "—"
    greeting = draft.get("greeting") or ""
    script = draft.get("script") or ""
    return (
        "Черновик звонка (сценарий):\n\n"
        f"Номер: {phone}\n\n"
        f"Greeting:\n«{greeting}»\n\n"
        f"Script:\n{script}\n\n"
        "Если ок — напишите «да, звони». Можно поправить текст."
    )


def _human_bytes(n: Any) -> str:
    try:
        size = int(n)
    except Exception:
        return ""
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _format_entry_meta(entry: dict[str, Any]) -> str:
    bits: list[str] = []
    size = _human_bytes(entry.get("bytes"))
    if size:
        bits.append(size)
    created = entry.get("created_at")
    modified = entry.get("modified_at")
    if created:
        bits.append(f"созд. {created}")
    if modified and modified != created:
        bits.append(f"изм. {modified}")
    elif modified and not created:
        bits.append(f"изм. {modified}")
    return f" ({'; '.join(bits)})" if bits else ""


def _format_files_browse(data: dict[str, Any]) -> str:
    source = str(data.get("source") or "mailru")
    path = str(data.get("path") or "/")
    account = data.get("account")
    dirs = data.get("dirs") or []
    files = data.get("files") or []
    mode = str(data.get("mode") or "list")
    query = data.get("query")
    title = {
        "mailru": "Mail.ru Облако",
        "yadisk": "Яндекс.Диск",
        "local": "Локальные файлы",
    }.get(source, source)
    lines = [f"{title}" + (f" ({account})" if account else "")]
    if mode == "search":
        lines.append(f"Поиск: «{query}» от {path}")
    else:
        lines.append(f"Путь: {path}")
    lines.append("")
    if dirs:
        lines.append("Папки:")
        for d in dirs[:80]:
            lines.append(
                f"• 📁 {d.get('name')}{_format_entry_meta(d)}  →  {d.get('path')}"
            )
        lines.append("")
    if files:
        lines.append("Файлы:")
        for f in files[:100]:
            lines.append(
                f"• 📄 {f.get('name')}{_format_entry_meta(f)}  →  {f.get('path')}"
            )
        lines.append("")
    if not dirs and not files:
        lines.append("(ничего не найдено)" if mode == "search" else "(пусто)")
        lines.append("")
    if mode == "search":
        lines.append("Открыть папку — browse_files(path=…). Скинуть файл — send_file.")
    else:
        lines.append(
            "Папка — напишите путь/имя. Поиск — «найди …». Файл — «скинь …»."
        )
    return "\n".join(lines).strip()


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
            {"query": query, "limit": limit, "max_chars": max_chars, "mode": "hybrid"},
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


def _autonomous_memory_search(
    knowledge: str,
    query: str,
    *,
    limit: int = 8,
    max_chars: int = 7000,
) -> dict[str, Any]:
    """Expand a user question into many queries and merge hits — never ask how to search."""
    try:
        from brain_platform.search.memory import memory_query_variants  # type: ignore
    except ImportError:
        import sys

        sys.path.insert(0, "/opt/ava-knowledge")
        from brain_platform.search.memory import memory_query_variants  # type: ignore

    variants = memory_query_variants(query)
    if not variants:
        variants = [query]

    matches: list[dict[str, Any]] = []
    seen_chunks: set[str] = set()
    threads: list[dict[str, Any]] = []
    seen_threads: set[str] = set()
    tried: list[str] = []
    q_tokens = [t.lower() for t in re.findall(r"[A-Za-zА-Яа-яЁё0-9@.-]+", query) if len(t) >= 3]

    for v in variants[:12]:
        tried.append(v)
        mem = _query_brain_search(
            knowledge,
            v,
            principal="service:text-secretary",
            limit=6,
            max_chars=2500,
        )
        for m in mem.get("matches") or []:
            cid = str(m.get("chunk_id") or m.get("document_id") or "")
            if cid and cid in seen_chunks:
                continue
            if cid:
                seen_chunks.add(cid)
            matches.append(m)
        try:
            th = _post_json(
                f"{knowledge}/api/brain/threads/list",
                {"q": v, "limit": 8},
                brain_principal="service:text-secretary",
                timeout=15.0,
            )
            for t in th.get("threads") or []:
                tid = str(t.get("id") or "")
                if tid and tid not in seen_threads:
                    seen_threads.add(tid)
                    threads.append(t)
        except Exception:
            pass

    def _rank(m: dict[str, Any]) -> int:
        title = str(m.get("title") or "").lower()
        snippet = str(m.get("snippet") or "").lower()
        blob = title + " " + snippet
        score = 0
        typ = m.get("type") or ""
        if typ == "email":
            score += 15
        elif typ == "contact":
            score += 8
        elif typ == "faq":
            score -= 5
        if "ооо" in blob or "инн" in blob:
            score += 25
        if "комплаен" in blob or "compliance" in blob:
            score += 10
        if "alfabank" in blob or "альфа" in blob or "mv_mmb" in blob:
            score += 12
        for t in q_tokens:
            if t in blob:
                score += 6
        return score

    ordered = sorted(matches, key=_rank, reverse=True)[: max(12, limit * 2)]

    parts: list[str] = []
    total = 0
    for m in ordered:
        title = m.get("title") or ""
        snip = m.get("snippet") or ""
        block = f"## {title}\n{snip}".strip()
        if not snip and not title:
            continue
        if total + len(block) > max_chars:
            break
        parts.append(block)
        total += len(block) + 2
    text = "\n\n".join(parts)

    if text.strip():
        summary = f"Найдены материалы по запросу ({len(ordered)} фрагм., тредов: {len(threads)})."
    else:
        summary = "По расширенному поиску устойчивых записей не нашлось."

    return {
        "ok": True,
        "query": query,
        "tried_queries": tried,
        "text": text,
        "chars": len(text),
        "matches": [
            {
                "document_id": m.get("document_id"),
                "chunk_id": m.get("chunk_id"),
                "title": m.get("title"),
                "type": m.get("type"),
                "has_snippet": bool(m.get("snippet")),
            }
            for m in ordered[:12]
        ],
        "threads": threads[:10],
        "summary": summary,
        "instruction_for_assistant": (
            "Ответь сразу по text/matches/threads. "
            "ЗАПРЕЩЕНО меню «поискать по email / ИНН / дате?». "
            "Если данных мало — сам вызови следующий tool с уточнением. "
            "Если после попыток всё ещё не хватает конкретного факта — "
            "задай ОДИН короткий вопрос (ИНН, ФИО, период, кого из найденных)."
        ),
    }


def _merge_knowledge(legacy: dict[str, Any], brain: dict[str, Any]) -> dict[str, Any]:
    """Second Brain is SoT; legacy keyword FAQ is fallback only."""
    legacy_text = str(legacy.get("text") or "").strip()
    brain_text = str(brain.get("text") or "").strip()
    parts: list[str] = []
    if brain_text:
        parts.append(brain_text)
    if legacy_text and legacy_text not in brain_text:
        # Keep legacy only when it adds something brain did not already return
        label = "— Legacy FAQ (fallback) —\n" if brain_text else ""
        parts.append(label + legacy_text)
    text = "\n\n".join(parts)
    if brain_text and legacy_text:
        source = "brain+legacy"
    elif brain_text:
        source = "brain"
    else:
        source = legacy.get("source") or "legacy"
    return {
        "ok": bool(legacy.get("ok") or brain.get("ok") or text),
        "topic": legacy.get("topic") or "",
        "topic_id": legacy.get("topic_id") or "",
        "text": text,
        "chars": len(text),
        "matches": brain.get("matches") or legacy.get("matches") or [],
        "brain_matches": brain.get("matches") or [],
        "legacy_matches": legacy.get("matches") or [],
        "source": source,
        "source_of_truth": "second_brain",
    }


def _autonomous_person_lookup(
    knowledge: str,
    *,
    q: str = "",
    email: str = "",
    phone: str = "",
    company: str = "",
) -> dict[str, Any]:
    """Multi-strategy person search without asking the user how to search."""
    try:
        from brain_platform.search.person import (  # type: ignore
            extract_emails,
            extract_phones,
            person_query_variants,
            score_contact_match,
        )
    except ImportError:
        import sys

        sys.path.insert(0, "/opt/ava-knowledge")
        from brain_platform.search.person import (  # type: ignore
            extract_emails,
            extract_phones,
            person_query_variants,
            score_contact_match,
        )

    tried: list[str] = []
    contacts_by_id: dict[str, dict[str, Any]] = {}
    variants = person_query_variants(q) if q else []
    if email:
        variants = [email, *variants]
    if company:
        variants = [company, *variants]
    if phone:
        variants = [phone, *variants]
    if not variants and q:
        variants = [q]

    for variant in variants[:15]:
        tried.append(variant)
        try:
            data = _post_json(
                f"{knowledge}/api/brain/contacts/find",
                {
                    "q": variant if "@" not in variant else "",
                    "email": email or (variant if "@" in variant else ""),
                    "phone": phone if variant == phone else "",
                    "company": company if variant == company else "",
                    "limit": 20,
                },
                brain_principal="service:text-secretary",
                timeout=15.0,
            )
        except Exception as exc:
            logger.warning("contact find failed for %r: %s", variant, exc)
            continue
        for c in data.get("contacts") or []:
            cid = str(c.get("id") or "")
            if not cid:
                continue
            prev = contacts_by_id.get(cid)
            score = score_contact_match(q or variant, c)
            if not prev or score > prev.get("_score", 0):
                contacts_by_id[cid] = {**c, "_score": score}

    ranked = sorted(contacts_by_id.values(), key=lambda c: c.get("_score", 0), reverse=True)
    # Drop contacts without a real email address
    cleaned_ranked = []
    for c in ranked:
        c.pop("_score", None)
        emails = []
        for e in c.get("emails") or []:
            m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", str(e))
            if m:
                emails.append(m.group(0).lower())
        if not emails:
            continue
        name = str(c.get("display_name") or "")
        if "@" in name or "<" in name or '"' in name:
            # Prefer local-part only as last resort; memory may supply better FIO
            name = emails[0].split("@")[0]
        c = {**c, "display_name": name, "emails": sorted(set(emails))}
        cleaned_ranked.append(c)
    ranked = cleaned_ranked

    memory_bits: list[str] = []
    memory_matches: list[dict[str, Any]] = []
    threads: list[dict[str, Any]] = []
    mem_queries = variants[:6] if variants else ([q] if q else [])
    for mq in mem_queries:
        if not mq:
            continue
        mem = _query_brain_search(
            knowledge,
            mq,
            principal="service:text-secretary",
            limit=4,
            max_chars=3500,
        )
        if mem.get("text"):
            memory_bits.append(str(mem["text"]))
        for m in mem.get("matches") or []:
            memory_matches.append(m)
        try:
            th = _post_json(
                f"{knowledge}/api/brain/threads/list",
                {"q": mq, "limit": 8},
                brain_principal="service:text-secretary",
                timeout=15.0,
            )
            for t in th.get("threads") or []:
                threads.append(t)
        except Exception:
            pass

    memory_text = "\n\n".join(memory_bits)[:8000]
    emails_found = extract_emails(memory_text)
    phones_found = extract_phones(memory_text)

    thread_by_id = {str(t.get("id")): t for t in threads if t.get("id")}
    threads = list(thread_by_id.values())[:10]

    hints: list[dict[str, Any]] = []
    if not ranked and (emails_found or phones_found or memory_text):
        hints.append(
            {
                "display_name": q or "из переписки",
                "emails": emails_found[:5],
                "phones": phones_found[:5],
                "company_name": None,
                "source": "memory-extract",
                "note": "Собрано из переписки",
            }
        )

    # Enrich top contact from memory phones/emails if sparse
    if ranked:
        top = ranked[0]
        if not top.get("phones") and phones_found:
            top = {**top, "phones": phones_found[:3]}
            ranked[0] = top
        # If display is still email-local but memory has Cyrillic FIO near query tokens
        if not re.search(r"[А-Яа-яЁё]", str(top.get("display_name") or "")):
            for line in memory_text.splitlines():
                if re.search(r"[А-Яа-яЁё]", line) and any(
                    t.lower() in line.lower() for t in (q or "").split() if len(t) > 2
                ):
                    m = re.search(r"([А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,3})", line)
                    if m:
                        top = {**top, "display_name": m.group(1)}
                        ranked[0] = top
                        break

    summary_parts = []
    if ranked:
        top = ranked[0]
        summary_parts.append(
            f"Найден контакт: {top.get('display_name')} | "
            f"email: {', '.join(top.get('emails') or []) or '—'} | "
            f"тел: {', '.join(top.get('phones') or []) or '—'} | "
            f"компания: {top.get('company_name') or '—'}"
        )
    elif hints:
        h = hints[0]
        summary_parts.append(
            f"В адресной книге точного ФИО нет, но в переписке: "
            f"email {', '.join(h.get('emails') or []) or '—'}, "
            f"тел {', '.join(h.get('phones') or []) or '—'}"
        )
    else:
        summary_parts.append("Пока не нашёл устойчивых контактов по запросу.")

    if threads:
        summary_parts.append(
            "Треды: "
            + "; ".join(f"{t.get('subject')} ({t.get('last_message_at')})" for t in threads[:3])
        )

    return {
        "ok": True,
        "query": q,
        "tried_queries": tried,
        "count": len(ranked),
        "contacts": ranked[:10],
        "memory_hints": hints,
        "emails_from_memory": emails_found[:10],
        "phones_from_memory": phones_found[:10],
        "threads": threads,
        "memory_preview": memory_text[:2500],
        "memory_match_count": len(memory_matches),
        "summary": " | ".join(summary_parts),
        "instruction_for_assistant": (
            "Ответь пользователю сразу фактами из summary/contacts/memory. "
            "Не спрашивай, искать ли по-другому — поиск уже выполнен автоматически."
        ),
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
            limit = int(arguments.get("limit") or 8)
            data = _autonomous_memory_search(
                knowledge,
                query,
                limit=limit,
                max_chars=7000,
            )
            return json.dumps(data, ensure_ascii=False)

        if name == "find_office_contact":
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Только для владельца"},
                    ensure_ascii=False,
                )
            data = _autonomous_person_lookup(
                knowledge,
                q=str(arguments.get("q") or ""),
                email=str(arguments.get("email") or ""),
                phone=str(arguments.get("phone") or ""),
                company=str(arguments.get("company") or ""),
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

        if name == "expand_office_graph":
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Только для владельца"},
                    ensure_ascii=False,
                )
            data = _post_json(
                f"{knowledge}/api/brain/graph/expand",
                {
                    "q": str(arguments.get("q") or ""),
                    "entity_id": arguments.get("entity_id") or None,
                    "depth": int(arguments.get("depth") or 1),
                    "limit": int(arguments.get("limit") or 40),
                },
                brain_principal="service:text-secretary",
            )
            # Keep payload compact for the model
            if isinstance(data, dict) and data.get("ok"):
                slim = {
                    "ok": True,
                    "summary": data.get("summary"),
                    "roots": data.get("roots") or [],
                    "entities": [
                        {
                            "id": e.get("id"),
                            "kind": e.get("kind"),
                            "name": e.get("canonical_name"),
                            "visibility": e.get("visibility"),
                        }
                        for e in (data.get("entities") or [])[:30]
                    ],
                    "edges": [
                        {
                            "from": e.get("source_entity_id"),
                            "to": e.get("target_entity_id"),
                            "rel": e.get("relation_type"),
                        }
                        for e in (data.get("edges") or [])[:40]
                    ],
                    "next_step_hint": (
                        "Если видишь company/person — можешь найти контакт "
                        "find_office_contact или письма search_office_memory."
                    ),
                }
                return json.dumps(slim, ensure_ascii=False)
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

        if name == "browse_files":
            source = str(arguments.get("source") or "mailru").strip().lower() or "mailru"
            if source in ("yandex", "yandex_disk"):
                source = "yadisk"
            if source in ("mailru_disk", "cloud_mail"):
                source = "mailru"
            path = str(arguments.get("path") or "/").strip() or "/"
            data = _post_json(
                f"{FILES_BASE}/api/files/list",
                {"source": source, "path": path},
                timeout=60.0,
            )
            if isinstance(data, dict) and data.get("ok"):
                data = {
                    **data,
                    "owner_message": _format_files_browse(data),
                    "instruction_for_assistant": (
                        "Покажи owner_message владельцу как есть. "
                        "Не спрашивай про доступ/аккаунт/корень — список уже получен. "
                        "Если просят открыть папку — browse_files с её path. "
                        "Поиск по имени — search_files. Файл — send_file."
                    ),
                }
            return json.dumps(data, ensure_ascii=False)

        if name == "search_files":
            source = str(arguments.get("source") or "mailru").strip().lower() or "mailru"
            if source in ("yandex", "yandex_disk"):
                source = "yadisk"
            if source in ("mailru_disk", "cloud_mail"):
                source = "mailru"
            query = str(arguments.get("query") or "").strip()
            path = str(arguments.get("path") or "/").strip() or "/"
            limit = int(arguments.get("limit") or 40)
            if len(query) < 2:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "query_too_short",
                        "message": "Нужен query от 2 символов",
                    },
                    ensure_ascii=False,
                )
            data = _post_json(
                f"{FILES_BASE}/api/files/search",
                {
                    "source": source,
                    "query": query,
                    "path": path,
                    "limit": max(1, min(limit, 100)),
                },
                timeout=120.0,
            )
            if isinstance(data, dict) and data.get("ok"):
                data = {
                    **data,
                    "owner_message": _format_files_browse(data),
                    "instruction_for_assistant": (
                        "Покажи owner_message как есть. Без вопросов про доступ. "
                        "Папка → browse_files(path). Файл → send_file."
                    ),
                }
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

        # ---- Quantum Console outbound (owner only) ----
        if name in (
            "draft_outbound_call",
            "outbound_dial",
            "get_outbound_scenario",
            "update_outbound_scenario",
            "list_outbound_calls",
            "await_outbound_result",
            "get_outbound_call",
        ):
            if not is_owner:
                return json.dumps(
                    {"ok": False, "error": "forbidden", "message": "Исходящие звонки только для владельца"},
                    ensure_ascii=False,
                )

        if name == "draft_outbound_call":
            goal = str(arguments.get("goal") or "").strip()
            if not goal:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "goal_required",
                        "message": "Нужна задача звонка (goal) из сообщения владельца",
                    },
                    ensure_ascii=False,
                )
            phone_raw = str(arguments.get("phone") or "").strip()
            phone = _normalize_dial_phone(phone_raw) if phone_raw else ""
            override = _synthesize_outbound_override(
                goal=goal,
                greeting=str(arguments["greeting"]) if arguments.get("greeting") is not None else None,
                script=str(arguments["script"]) if arguments.get("script") is not None else None,
                use_knowledge=False,
                callee_name=str(arguments.get("callee_name") or ""),
                on_behalf_of=str(arguments.get("on_behalf_of") or ""),
            )
            draft = {
                "ok": True,
                "phone": phone or None,
                "goal": goal,
                "greeting": override.get("greeting"),
                "script": override.get("script"),
                "use_knowledge": False,
                "owner_message": _format_draft_for_owner(
                    {
                        "phone": phone or phone_raw or "—",
                        "greeting": override.get("greeting"),
                        "script": override.get("script"),
                    }
                ),
                "instruction_for_assistant": (
                    "Вставь owner_message владельцу КАК ЕСТЬ (или тот же Greeting+Script). "
                    "Нельзя отвечать без текста сценария. Жди «да, звони», потом outbound_dial "
                    "с этими greeting/script/goal/phone."
                ),
            }
            return json.dumps(draft, ensure_ascii=False)

        if name == "outbound_dial":
            if not bool(arguments.get("confirm")):
                return json.dumps(
                    {
                        "ok": False,
                        "error": "confirm_required",
                        "message": (
                            "Сначала подтверди у владельца номер и цель. "
                            "После явного «да, звони» вызови снова с confirm=true."
                        ),
                    },
                    ensure_ascii=False,
                )
            phone = _normalize_dial_phone(str(arguments.get("phone") or ""))
            if not (phone.startswith("7") and len(phone) == 11):
                return json.dumps(
                    {
                        "ok": False,
                        "error": "bad_phone",
                        "message": "Нужен номер в формате 79XXXXXXXXX",
                        "normalized": phone,
                    },
                    ensure_ascii=False,
                )
            ctx = str(arguments.get("context") or "outbound").strip().lower() or "outbound"
            if ctx != "outbound":
                return json.dumps(
                    {
                        "ok": False,
                        "error": "context_forbidden",
                        "message": "Из Telegram разрешён только context=outbound",
                    },
                    ensure_ascii=False,
                )
            body: dict[str, Any] = {"phone": phone, "context": "outbound"}
            goal = str(arguments.get("goal") or "").strip()
            greeting = arguments.get("greeting")
            script = arguments.get("script")
            if script is None and arguments.get("prompt") is not None:
                script = arguments.get("prompt")
            use_knowledge_arg = (
                arguments.get("use_knowledge")
                if "use_knowledge" in arguments and arguments.get("use_knowledge") is not None
                else None
            )
            use_default = bool(arguments.get("use_default_script"))
            override = _synthesize_outbound_override(
                goal=goal,
                greeting=str(greeting) if greeting is not None else None,
                script=str(script) if script is not None else None,
                use_knowledge=use_knowledge_arg,
            )
            if not override and not use_default:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "goal_or_script_required",
                        "message": (
                            "Нужен goal и/или script с задачей звонка из чата. "
                            "Без этого Console возьмёт старый сценарий про массовые выплаты. "
                            "Если нужен именно постоянный YAML — вызови с use_default_script=true."
                        ),
                    },
                    ensure_ascii=False,
                )
            body.update(override)
            dialed_at = _utc_now_iso()
            data = _console_request(
                "POST",
                "/api/outbound/dial",
                body=body,
                timeout=45.0,
            )
            if isinstance(data, dict):
                data = {
                    **data,
                    "phone": phone,
                    "goal": goal,
                    "dialed_at": dialed_at,
                    "per_call_override": {
                        "greeting": bool(body.get("greeting")),
                        "script": bool(body.get("script")),
                        "use_knowledge": body.get("use_knowledge"),
                        "synthesized_from_goal": bool(goal) and not bool(script),
                        "use_default_script": use_default and not bool(override),
                    },
                    "hint": (
                        "Звонок ЗАПУЩЕН. НЕ вызывай list/get сразу — там будет СТАРЫЙ звонок. "
                        "Для отчёта вызови await_outbound_result(phone, dialed_after=dialed_at). "
                        "Сводку пиши только по conversation из await."
                    ),
                    "next_tool": {
                        "name": "await_outbound_result",
                        "arguments": {"phone": phone, "dialed_after": dialed_at},
                    },
                }
            return json.dumps(data, ensure_ascii=False)

        if name == "get_outbound_scenario":
            ctx = str(arguments.get("context") or "outbound").strip().lower() or "outbound"
            if ctx != "outbound":
                return json.dumps(
                    {"ok": False, "error": "context_forbidden", "message": "Только outbound"},
                    ensure_ascii=False,
                )
            data = _console_request("GET", "/api/outbound/script")
            if isinstance(data, dict):
                script_text = str(data.get("script") or data.get("prompt") or "")
                data = {
                    **data,
                    "script_chars": len(script_text),
                    "script_preview": script_text[:1200]
                    + ("…" if len(script_text) > 1200 else ""),
                    # alias for older prompts
                    "prompt_chars": len(script_text),
                    "prompt_preview": script_text[:1200]
                    + ("…" if len(script_text) > 1200 else ""),
                }
            return json.dumps(data, ensure_ascii=False)

        if name == "update_outbound_scenario":
            greeting = arguments.get("greeting")
            script = arguments.get("script")
            if script is None and arguments.get("prompt") is not None:
                script = arguments.get("prompt")
            use_knowledge = arguments.get("use_knowledge")
            if greeting is None and script is None and use_knowledge is None:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "nothing_to_update",
                        "message": "Передай greeting и/или script (или use_knowledge)",
                    },
                    ensure_ascii=False,
                )
            body = {}
            if greeting is not None:
                body["greeting"] = str(greeting)
            if script is not None:
                body["script"] = str(script)
            if use_knowledge is not None:
                body["use_knowledge"] = bool(use_knowledge)
            data = _console_request("PUT", "/api/outbound/script", body=body, timeout=45.0)
            restart_info: dict[str, Any] | None = None
            if bool(arguments.get("restart_engine")):
                try:
                    restart_info = _console_request(
                        "POST", "/api/actions/restart-engine", body={}, timeout=60.0
                    )
                except Exception as exc:  # noqa: BLE001
                    restart_info = {"ok": False, "error": str(exc)}
            out = {
                "ok": bool(data.get("ok", True)) if isinstance(data, dict) else True,
                "saved": data,
                "restart_engine": restart_info,
                "note": "Изменён постоянный outbound script; входящий default не тронут.",
            }
            return json.dumps(out, ensure_ascii=False)

        if name == "list_outbound_calls":
            ctx = str(arguments.get("context") or "outbound").strip().lower() or "outbound"
            limit = int(arguments.get("limit") or 15)
            phone_filter = _normalize_dial_phone(str(arguments.get("phone") or ""))
            data = _console_request(
                "GET",
                "/api/calls",
                query={"limit": max(1, min(limit, 50)), "context": ctx},
            )
            if isinstance(data, dict) and data.get("calls"):
                slim_calls = []
                for c in data.get("calls") or []:
                    num = _normalize_dial_phone(str(c.get("caller_number") or ""))
                    if phone_filter and num != phone_filter:
                        continue
                    slim_calls.append(
                        {
                            "call_id": c.get("call_id"),
                            "caller_number": c.get("caller_number"),
                            "start_time": c.get("start_time"),
                            "duration_seconds": c.get("duration_seconds"),
                            "outcome": c.get("outcome"),
                            "context_name": c.get("context_name"),
                            "transcript_preview": (c.get("transcript_preview") or "")[:240],
                        }
                    )
                data = {
                    "ok": True,
                    "total": len(slim_calls),
                    "filter_context": data.get("filter_context") or ctx,
                    "filter_phone": phone_filter or None,
                    "calls": slim_calls,
                    "warning": (
                        "Если только что был dial — для отчёта используй await_outbound_result, "
                        "иначе легко взять СТАРЫЙ звонок."
                    ),
                }
            return json.dumps(data, ensure_ascii=False)

        if name == "await_outbound_result":
            return json.dumps(
                _await_outbound_result(
                    str(arguments.get("phone") or ""),
                    dialed_after=str(arguments.get("dialed_after") or "") or None,
                    timeout_sec=int(arguments.get("timeout_sec") or 180),
                ),
                ensure_ascii=False,
            )

        if name == "get_outbound_call":
            call_id = str(arguments.get("call_id") or "").strip()
            if not call_id:
                return json.dumps(
                    {"ok": False, "error": "call_id_required"},
                    ensure_ascii=False,
                )
            data = _console_request(
                "GET",
                f"/api/calls/{urllib.parse.quote(call_id, safe='')}",
            )
            if isinstance(data, dict) and isinstance(data.get("call"), dict):
                data = _slim_call_conversation(data["call"], call_id=call_id)
            return json.dumps(data, ensure_ascii=False)

        return json.dumps({"ok": False, "error": f"unknown tool: {name}"})
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("tool %s HTTP %s: %s", name, exc.code, err)
        return json.dumps({"ok": False, "error": err or str(exc)})
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return json.dumps({"ok": False, "error": str(exc)})
