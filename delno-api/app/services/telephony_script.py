"""Per-tenant telephony script + tools — configured via Hermes onboarding."""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.knowledge_documents import upsert_tenant_knowledge_document
from app.services.onboarding_templates import get_template

AVAILABLE_TOOLS: list[dict[str, str]] = [
    {
        "id": "get_company_knowledge",
        "title": "База знаний",
        "hint": "Ответы о компании/услугах из Знаний",
    },
    {
        "id": "check_calendar",
        "title": "Проверка календаря",
        "hint": "Свободен ли слот",
    },
    {
        "id": "create_calendar_event",
        "title": "Создать встречу",
        "hint": "Событие + ВКС (если connector включён)",
    },
    {
        "id": "send_welcome_email",
        "title": "Welcome-письмо",
        "hint": "Презентация / материалы на email",
    },
    {
        "id": "send_email",
        "title": "Письмо",
        "hint": "Произвольное письмо клиенту",
    },
    {
        "id": "create_conference",
        "title": "Только ВКС",
        "hint": "Ссылка на конференцию без слота",
    },
    {
        "id": "hangup_call",
        "title": "Завершить звонок",
        "hint": "Вежливое прощание и hangup",
    },
]

_DEFAULT_TOOLS = [
    "get_company_knowledge",
    "check_calendar",
    "create_calendar_event",
    "hangup_call",
]

_TOOL_IDS = {t["id"] for t in AVAILABLE_TOOLS}


def _settings(tenant: Tenant) -> dict[str, Any]:
    return dict(tenant.settings) if isinstance(tenant.settings, dict) else {}


def _telephony_block(settings: dict[str, Any]) -> dict[str, Any]:
    block = settings.get("telephony")
    return dict(block) if isinstance(block, dict) else {}


def get_telephony_config(db: Session, ctx: TenantContext) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tel = _telephony_block(_settings(tenant))
    script = (tel.get("script") or "").strip()
    greeting = (tel.get("greeting") or "").strip()
    tools = [t for t in (tel.get("tools") or _DEFAULT_TOOLS) if t in _TOOL_IDS]
    return {
        "ok": True,
        "configured": bool(script),
        "greeting": greeting,
        "script": script,
        "tools": tools,
        "available_tools": AVAILABLE_TOOLS,
        "updated_at": tel.get("updated_at"),
        "source": tel.get("source") or None,
    }


def save_telephony_script(
    db: Session,
    ctx: TenantContext,
    *,
    script: str,
    greeting: str | None = None,
    tools: list[str] | None = None,
    source: str = "hermes",
    publish_knowledge: bool = True,
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    tel = _telephony_block(settings)
    body = (script or "").strip()
    if len(body) < 40:
        return {"ok": False, "error": "script_too_short"}

    greets = greeting
    if greets is None:
        greets = _extract_greeting(body) or tel.get("greeting") or ""

    chosen = tools if tools is not None else tel.get("tools") or _parse_tools_from_markdown(body) or list(_DEFAULT_TOOLS)
    chosen = [t for t in chosen if t in _TOOL_IDS]
    if "hangup_call" not in chosen:
        chosen.append("hangup_call")
    if "get_company_knowledge" not in chosen:
        chosen.insert(0, "get_company_knowledge")

    from datetime import datetime, timezone

    tel.update(
        {
            "script": body,
            "greeting": (greets or "").strip()[:500],
            "tools": chosen,
            "source": source,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    settings["telephony"] = tel
    hermes = dict(settings.get("hermes") or {}) if isinstance(settings.get("hermes"), dict) else {}
    hermes["telephony_script_ready"] = True
    settings["hermes"] = hermes
    tenant.settings = settings
    db.add(tenant)

    kb: dict[str, Any] | None = None
    if publish_knowledge:
        kb = upsert_tenant_knowledge_document(
            db,
            tenant,
            title="Сценарий телефонного секретаря",
            body=body,
            visibility="company",
            source="tenant.telephony_script",
        )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="telephony.script.saved",
        payload={"source": source, "tools": chosen, "greeting": greets},
    )
    db.commit()
    db.refresh(tenant)
    return {
        "ok": True,
        "configured": True,
        "greeting": greets,
        "tools": chosen,
        "script_chars": len(body),
        "knowledge": kb,
        "message_ru": "Сценарий секретаря сохранён. Можно включать tools и делать тестовый звонок.",
    }


def set_telephony_tools(
    db: Session,
    ctx: TenantContext,
    *,
    tools: list[str],
) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    tel = _telephony_block(settings)
    if not (tel.get("script") or "").strip():
        return {"ok": False, "error": "script_missing", "message_ru": "Сначала сохраните сценарий."}
    chosen = [t for t in tools if t in _TOOL_IDS]
    if not chosen:
        return {"ok": False, "error": "empty_tools"}
    if "hangup_call" not in chosen:
        chosen.append("hangup_call")
    tel["tools"] = chosen
    settings["telephony"] = tel
    tenant.settings = settings
    db.add(tenant)
    db.commit()
    return {
        "ok": True,
        "tools": chosen,
        "available_tools": AVAILABLE_TOOLS,
        "message_ru": "Tools для линии обновлены: " + ", ".join(chosen),
    }


def formalize_rough_script(raw: str, *, company_name: str | None = None) -> str:
    """Turn rough owner dictation into a structured telephony script markdown."""
    text = (raw or "").strip()
    brand = (company_name or "вашей компании").strip()
    greeting = _extract_greeting(text) or f"Добрый день! Вы позвонили в {brand}. Чем могу помочь?"
    tools = _parse_tools_from_markdown(text) or list(_DEFAULT_TOOLS)
    tool_lines = "\n".join(
        f"- [{'x' if t['id'] in tools else ' '}] {t['id']} — {t['hint']}" for t in AVAILABLE_TOOLS
    )
    return f"""# Сценарий телефонного секретаря

## Приветствие

{greeting}

## Кто вы на линии

- Как представляться: ИИ-секретарь компании {brand}
- Честно говорить, что вы ИИ: да

## Цель звонка

- Ответить на вопросы о компании / услугах
- Записать на встречу при интересе

## Исходный рассказ владельца

{text}

## Правила речи

- Только русский язык, коротко и по делу
- Не озвучивать технические детали tools
- Не выдумывать факты вне базы знаний

## База знаний

- Детали продукта/цен — через get_company_knowledge

## Запись на встречу

1. Имя (подтвердить)
2. Email (повторить вслух и подтвердить)
3. Дата и время
4. check_calendar → при свободном слоте create_calendar_event
5. Финальная фраза: «Готово, встреча зафиксирована. Приглашение отправлено на почту.»

## Tools

{tool_lines}

## Завершение

Спасибо, хорошего дня!
""".strip()


def propose_script_from_knowledge(
    db: Session,
    ctx: TenantContext,
    *,
    knowledge_snippet: str | None = None,
    company_name: str | None = None,
) -> dict[str, Any]:
    """Draft a script from company knowledge / blank template — no QL hardcoding."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    settings = _settings(tenant)
    brand = (
        company_name
        or settings.get("assistant_company")
        or settings.get("company_name")
        or tenant.name
        or "компании"
    )
    blank = get_template("telephony-script")
    base = (blank or {}).get("body") or ""
    snippet = (knowledge_snippet or "").strip()
    draft = formalize_rough_script(
        snippet
        or (
            f"Компания {brand}. На линии ИИ-секретарь отвечает на вопросы по услугам "
            f"и записывает на короткий созвон. Факты брать из базы знаний."
        ),
        company_name=str(brand),
    )
    if base and not snippet:
        # Keep blank checklist structure but with brand greeting filled.
        draft = base.replace("…", f"(укажите для {brand})", 1)
        draft = re.sub(
            r"(Текст первой фразы[^\n]*:\n).*",
            rf"\1Добрый день! Вы позвонили в {brand}. Чем могу помочь?",
            draft,
            count=1,
        )
    return {
        "ok": True,
        "draft": draft,
        "company_name": brand,
        "message_ru": (
            "Вот черновик сценария. Скажите «сохрани сценарий» — запишу его, "
            "или поправьте голосом/текстом."
        ),
    }


def inbound_script_for_tenant(db: Session, tenant_id) -> dict[str, Any]:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
    if not tenant:
        return {}
    tel = _telephony_block(_settings(tenant))
    script = (tel.get("script") or "").strip()
    if not script:
        return {}
    return {
        "script": script,
        "greeting": (tel.get("greeting") or "").strip(),
        "tools": tel.get("tools") or list(_DEFAULT_TOOLS),
    }


def _extract_greeting(text: str) -> str | None:
    m = re.search(
        r"(?im)^(?:##\s*Приветствие\s*\n+|>\s*)?([^\n]{12,200})",
        text or "",
    )
    if not m:
        m = re.search(r"(?i)приветств[^\n]*:\s*([^\n]{12,200})", text or "")
    if not m:
        return None
    line = m.group(1).strip().lstrip("#").strip()
    if line.lower().startswith("текст первой"):
        return None
    if "…" in line or line.startswith("-"):
        return None
    return line[:500]


def _parse_tools_from_markdown(text: str) -> list[str] | None:
    found: list[str] = []
    lower = text or ""
    for tid in _TOOL_IDS:
        # checked markdown boxes or bare mentions under Tools
        if re.search(rf"\[x\]\s*`?{re.escape(tid)}`?", lower, re.I):
            found.append(tid)
        elif re.search(rf"(?m)^\s*-\s*\[x\][^\n]*{re.escape(tid)}", lower, re.I):
            found.append(tid)
    return found or None
