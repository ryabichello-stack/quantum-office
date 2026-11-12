"""Operator LLM loop — read-only KB + cabinet live setup."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.operator.setup_intent import parse_setup_intent
from app.operator.tools.registry import (
    PendingConfirmation,
    ToolResult,
    registry,
    requires_confirmation,
    tool_confirmation_class,
)
from app.services.audit import write_audit
from app.services.billing import record_llm_usage
from app.services.events import emit_event
from app.services.model_provider import get_model_provider
from app.services.provenance import extract_sources_from_knowledge


def _charge_llm_if_any(
    db: Session,
    ctx: TenantContext,
    completion: dict[str, Any],
    *,
    channel: str | None = None,
) -> None:
    usage = completion.get("usage") if isinstance(completion.get("usage"), dict) else {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    if prompt or completion_tokens:
        try:
            record_llm_usage(
                db,
                ctx,
                prompt_tokens=prompt,
                completion_tokens=completion_tokens,
                model=str(completion.get("model") or "") or None,
                channel=channel,
            )
        except Exception:  # noqa: BLE001
            pass


# Owner/Hermes cabinet allowlist — setup + health + office + telephony
CABINET_LLM_TOOLS = (
    "get_tenant_summary",
    "update_tenant_settings",
    "upload_knowledge_snippet",
    "set_feature_flag",
    "get_knowledge",
    # Hermes setup / health
    "hermes.setup_status",
    "hermes.setup_mark",
    "hermes.health",
    "hermes.alerts",
    # Phones + calls
    "phones.list",
    "phones.provision",
    "calls.list",
    "calls.get",
    "calls.dial",
    "calls.jobs",
    # Office connectors
    "suggest_calendar_slots",
    "send_mail_draft",
    "list_files",
    "create_conference",
    # Hermes web browser
    "web.search",
    "web.fetch",
    "web.browse",
    "office.import_website",
    "billing.summary",
)


def run_operator_turn(
    db: Session,
    ctx: TenantContext,
    *,
    message: str,
    channel: str = "web",
    conversation_id: uuid.UUID | None = None,
    input_modality: str = "text",
    record_user_message: bool = True,
    commit: bool = True,
    attachments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Single operator turn. Text and voice (post-STT) use the same path.
    Voice output (TTS) is handled by the client or a future /operator/voice route.
    Optional attachments: images (vision) and text/docs.
    """
    from app.services.operator_attachments import normalize_attachments

    try:
        normalized = normalize_attachments(attachments)
        if not normalized.get("ok"):
            return {
                "conversation_id": str(conversation_id) if conversation_id else None,
                "reply": f"Не удалось принять вложение: {normalized.get('error')}",
                "sources": [],
                "tool_calls": [{"tool": "attachments", "ok": False, "error": normalized.get("error")}],
                "pending_confirmation": None,
                "pending_credential_form": None,
                "modality": input_modality,
            }

        from app.services.tenant_vault import looks_like_credential_paste

        conversation = _get_or_create_conversation(db, ctx, channel, conversation_id)
        display_message = message.strip()
        if normalized.get("summary_labels"):
            label_line = " ".join(normalized["summary_labels"])
            display_message = f"{display_message}\n{label_line}".strip() if display_message else label_line
        # Never persist raw passwords/logins in the chat transcript.
        if looks_like_credential_paste(display_message or message):
            display_message = "[логин/пароль — через безопасную форму, не в ленте чата]"

        if record_user_message:
            meta_user: dict[str, Any] = {"modality": input_modality}
            if normalized.get("items"):
                meta_user["attachments"] = [
                    {
                        "filename": i.get("filename"),
                        "content_type": i.get("content_type"),
                        "kind": i.get("kind"),
                        "size": i.get("size"),
                    }
                    for i in normalized["items"]
                ]
            if looks_like_credential_paste(message):
                meta_user["redacted_secret"] = True
            db.add(
                Message(
                    tenant_id=ctx.tenant_id,
                    conversation_id=conversation.id,
                    role="user",
                    body=display_message or message,
                    meta=meta_user,
                )
            )
            db.flush()

        reply, tool_calls, sources, pending, credential_form = _generate_reply(
            db,
            ctx,
            message,
            channel=channel,
            attachments=normalized,
            conversation_id=conversation.id,
        )

        suggested_actions: list[dict[str, str]] = []
        for tc in tool_calls or []:
            if isinstance(tc, dict) and isinstance(tc.get("suggested_actions"), list):
                suggested_actions = [
                    a
                    for a in tc["suggested_actions"]
                    if isinstance(a, dict) and a.get("title") and a.get("text")
                ]
                break

        meta: dict[str, Any] = {"tool_calls": tool_calls, "sources": sources}
        if pending:
            meta["pending_confirmation"] = pending
        if credential_form:
            meta["pending_credential_form"] = {
                "kind": credential_form.get("kind"),
                "title": credential_form.get("title"),
            }
        if suggested_actions:
            meta["suggested_actions"] = suggested_actions

        db.add(
            Message(
                tenant_id=ctx.tenant_id,
                conversation_id=conversation.id,
                role="assistant",
                body=reply,
                meta=meta,
            )
        )
        write_audit(
            db,
            ctx,
            action="operator.chat",
            resource=f"conversation:{conversation.id}",
            new_value={"channel": channel, "modality": input_modality},
        )
        if commit:
            db.commit()
        else:
            db.flush()

        return {
            "conversation_id": str(conversation.id),
            "reply": reply,
            "tool_calls": tool_calls,
            "sources": sources,
            "modality": input_modality,
            "pending_confirmation": pending,
            "pending_credential_form": credential_form,
            "suggested_actions": suggested_actions,
        }
    except Exception as exc:
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="operator.error",
            category="operational",
            source="operator.chat",
            payload={
                "conversation_id": str(conversation_id) if conversation_id else None,
                "channel": channel,
                "modality": input_modality,
                "error": str(exc)[:500],
                "stage": "run_operator_turn",
            },
        )
        if commit:
            db.commit()
        else:
            db.flush()
        raise


def _get_or_create_conversation(
    db: Session,
    ctx: TenantContext,
    channel: str,
    conversation_id: uuid.UUID | None,
) -> Conversation:
    if conversation_id:
        row = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.tenant_id == ctx.tenant_id)
            .one_or_none()
        )
        if row:
            return row
    row = Conversation(tenant_id=ctx.tenant_id, channel=channel)
    db.add(row)
    db.flush()
    return row


def _kb_context_from_result(result: ToolResult) -> str:
    data = result.data or {}
    text = str(data.get("text") or "").strip()
    if text:
        return text[:4000]
    matches = data.get("matches") or data.get("results") or []
    snippets: list[str] = []
    for item in matches[:5]:
        if isinstance(item, dict):
            snippet = str(item.get("snippet") or item.get("text") or "").strip()
            if snippet:
                snippets.append(snippet)
    return "\n\n".join(snippets)[:4000]


def _conversation_history_for_llm(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    conversation_id: uuid.UUID,
    limit: int = 24,
) -> list[dict[str, str]]:
    """Prior turns for the model. Excludes the latest user message (added separately)."""
    rows = (
        db.query(Message)
        .filter(Message.tenant_id == tenant_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(max(limit + 1, 2))
        .all()
    )
    rows = list(reversed(rows))
    if rows and rows[-1].role == "user":
        rows = rows[:-1]
    out: list[dict[str, str]] = []
    for row in rows[-limit:]:
        role = "assistant" if row.role == "assistant" else "user"
        body = (row.body or "").strip()
        if not body:
            continue
        out.append({"role": role, "content": body[:3000]})
    return out


def _try_secret_form_turn(
    message: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None, dict[str, Any] | None] | None:
    from app.services.tenant_vault import (
        credential_form_spec,
        looks_like_credential_paste,
        parse_credential_paste,
        wants_sip_secret_form,
    )

    if not wants_sip_secret_form(message):
        return None
    prefill = parse_credential_paste(message) if looks_like_credential_paste(message) else None
    form = credential_form_spec("mango_sip", prefill=prefill)
    if looks_like_credential_paste(message):
        reply = (
            "Не вставляйте пароль в чат — это небезопасно и я его не принимаю текстом.\n"
            "Заполните безопасную форму ниже: логин и SIP-пароль сохранятся только в кабинете."
        )
    else:
        reply = (
            "Для SIP Mango откройте безопасную форму ниже. "
            "Пароль не попадёт в историю переписки."
        )
    return reply, [{"tool": "credentials.form", "ok": True, "kind": "mango_sip"}], [], None, form


def _try_kb_credential_lookup(
    db: Session,
    ctx: TenantContext,
    message: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None] | None:
    lower = (message or "").lower()
    if not any(
        w in lower
        for w in (
            "пароль",
            "логин",
            "password",
            "login",
            "учётк",
            "учетк",
            "доступ",
            "credential",
            "smtp",
            "imap",
            "ключ api",
            "api key",
            "токен бота",
        )
    ):
        return None
    result = registry.run(db, ctx, "get_knowledge", query=message)
    tool_calls: list[dict[str, Any]] = [{"tool": "get_knowledge", "ok": isinstance(result, ToolResult) and result.ok}]
    if not isinstance(result, ToolResult) or not result.ok:
        return (
            "Не смог прочитать базу знаний. Откройте раздел «Знания» или повторите запрос.",
            tool_calls,
            [],
            None,
        )
    text = _kb_context_from_result(result)
    sources = extract_sources_from_knowledge(result.data)
    if not text.strip():
        return (
            "В базе знаний по логину/паролю/доступу ничего не нашёл. "
            "Добавьте запись («добавь в базу знаний: …») или загрузите документ в Знания.",
            tool_calls,
            sources,
            None,
        )
    return (
        "Нашёл в базе знаний (служебные данные — не пересылайте третьим лицам):\n\n"
        f"{text[:2500]}",
        tool_calls,
        sources,
        None,
    )


def _system_prompt(
    ctx: TenantContext,
    kb_context: str,
    *,
    cabinet: bool = False,
    onboarding: bool = False,
    widget: bool = False,
) -> str:
    if onboarding:
        base = (
            f"Ты DELNO — помогаешь владельцу настроить ИИ-сотрудника для компании «{ctx.tenant_slug}». "
            "Это первичный onboarding через разговор: собирай знания о бизнесе естественно. "
            "Пользователь может прислать текст, ссылку на сайт или документы. "
            "Не проси «заполнить базу знаний» или «настроить KB» — просто разговаривай. "
            "Задавай 1–2 осмысленных уточняющих вопроса за шаг, исходя из пробелов. "
            "Все данные сначала попадают в черновик (draft) — не публикуй без явного подтверждения владельца. "
            "Если сайт не удалось прочитать — не показывай техническую ошибку, предложи рассказать или загрузить материалы."
        )
        if kb_context:
            return f"{base}\n\n--- Черновик знаний ---\n{kb_context}"
        return base

    base = (
        f"Ты DELNO — ИИ-сотрудник компании (tenant: {ctx.tenant_slug}). "
        "Отвечай кратко по-русски. Используй только факты из базы знаний ниже. "
        "Если данных недостаточно — честно скажи об этом и предложи оставить заявку на сайте. "
        "Не выдумывай цены, условия и действия. Не запрашивай tenant_id и не выполняй массовые операции."
    )
    if cabinet:
        base += (
            " Ты Hermes в кабинете владельца: помнишь предыдущие реплики этого диалога. "
            "Отвечай по контексту беседы, не начинай с нуля. "
            "Помогай настраивать офис (KB, каналы, телефон, коннекторы). "
            "Если спрашивают логин/пароль/доступ — сначала ищи в базе знаний (get_knowledge), "
            "не говори «нет данных» без поиска. Изменения-записи — только после подтверждения."
        )
    if widget:
        base += (
            " Ты на публичном сайте DELNO в демо-режиме для посетителей. "
            "Отвечай коротко (2–4 предложения), только по фактам из базы знаний ниже. "
            "По ценам: «Диалоги» 2 990 ₽/мес, «Диалоги + звонки» 5 990 ₽/мес. "
            "Не обещай подключение, запись или звонок без менеджера. "
            "Если данных нет — предложи оставить контакт или написать на office@dlno.ru."
        )
    if kb_context:
        return f"{base}\n\n--- База знаний ---\n{kb_context}"
    return base


def _format_hermes_setup(data: dict[str, Any]) -> str:
    progress = data.get("progress") or {}
    done = progress.get("required_done", 0)
    total = progress.get("required_total", 0)
    lines = [
        data.get("message_ru") or "Статус сетапа офиса.",
        f"Прогресс: {done}/{total}.",
    ]
    checks = data.get("checks") or {}
    steps = data.get("steps") or []
    for step in steps:
        sid = step.get("id")
        check = checks.get(sid) or {}
        mark = "✓" if check.get("ok") else ("·" if check.get("optional") else "○")
        hint = step.get("hint") or ""
        title = step.get("title") or sid
        lines.append(f"{mark} {title}" + ("" if check.get("ok") else f" — {hint}"))
    next_steps = data.get("next_steps") or []
    if next_steps:
        nxt = next_steps[0]
        lines.append(f"Следующий шаг: {nxt.get('title')} — {nxt.get('hint')}")
    lines.append("Скажите голосом или текстом, что подключить дальше (Telegram, номер, почта…).")
    return "\n".join(lines)


def _format_hermes_health(data: dict[str, Any]) -> str:
    lines = [data.get("message_ru") or ("Офис в порядке." if data.get("healthy") else "Есть проблемы.")]
    for alert in (data.get("alerts") or [])[:6]:
        fix = alert.get("fix") or ""
        lines.append(f"• {alert.get('message_ru')}" + (f" → {fix}" if fix else ""))
    tel = data.get("telephony") or {}
    if tel:
        dids = tel.get("active_dids") or []
        lines.append(
            f"Телефония: DID {', '.join(dids) if isinstance(dids, list) else dids or '—'}; "
            f"очередь {tel.get('queued_jobs', 0)}, зависло {tel.get('stuck_jobs', 0)}."
        )
    return "\n".join(lines)


def _format_calls_list(data: dict[str, Any]) -> str:
    items = data.get("items") or []
    if not items:
        return "Звонков пока нет. Когда появятся входящие на DID или исходящие задания — увидите их здесь."
    lines = ["Последние звонки:"]
    for item in items[:8]:
        direction = item.get("direction") or "?"
        state = item.get("state") or "?"
        frm = item.get("from_e164") or "—"
        to = item.get("to_e164") or "—"
        lines.append(f"• {direction} · {state}: {frm} → {to}")
    return "\n".join(lines)


def _format_tenant_summary(data: dict[str, Any]) -> str:
    lines = [f"Компания: {data.get('tenant_name', '—')}"]
    settings = data.get("settings") or {}
    if settings.get("assistant_name"):
        lines.append(f"Имя ассистента: {settings['assistant_name']}")
    if settings.get("greeting"):
        lines.append(f"Приветствие: {settings['greeting']}")
    legal = settings.get("legal") or {}
    if legal.get("company_name"):
        lines.append(f"Юр. лицо: {legal['company_name']}")
    flags = data.get("feature_flags") or {}
    if flags:
        enabled = [k for k, v in flags.items() if v]
        disabled = [k for k, v in flags.items() if not v]
        if enabled:
            lines.append("Включено: " + ", ".join(enabled))
        if disabled:
            lines.append("Выключено: " + ", ".join(disabled))
    return "\n".join(lines)


def _pending_confirmation_dict(
    tool_name: str,
    params: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    return {
        "confirmation_id": str(uuid.uuid4()),
        "tool_name": tool_name,
        "params": params,
        "summary": summary,
    }


def _parse_tool_args(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _tool_summary(tool_name: str, params: dict[str, Any]) -> str:
    if tool_name == "upload_knowledge_snippet":
        return f"Добавить в KB: «{params.get('title', 'документ')}»"
    if tool_name == "set_feature_flag":
        state = "Включить" if params.get("enabled") else "Выключить"
        return f"{state} «{params.get('flag_key', 'flag')}»"
    if tool_name == "update_tenant_settings":
        keys = list((params.get("patch") or {}).keys())
        return f"Обновить настройки: {', '.join(keys) or 'patch'}"
    if tool_name == "office.import_website":
        return f"Импорт сайта: {params.get('url') or params.get('message') or 'URL'}"
    if tool_name == "get_tenant_summary":
        return "Показать текущие настройки"
    if tool_name == "hermes.setup_status":
        return "Статус сетапа офиса"
    if tool_name == "hermes.health":
        return "Проверить здоровье офиса"
    if tool_name == "hermes.alerts":
        return "Алерты офиса"
    if tool_name == "calls.list":
        return "Список звонков"
    return tool_name.replace("_", " ")


def _execute_cabinet_tool(
    db: Session,
    ctx: TenantContext,
    tool_name: str,
    params: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    summary = _tool_summary(tool_name, params)
    tool_calls: list[dict[str, Any]] = [{"tool": tool_name, "ok": None}]

    tool = registry.get(tool_name)
    if not tool:
        tool_calls[0]["ok"] = False
        return f"Инструмент «{tool_name}» недоступен.", tool_calls, [], None

    tool_calls[0]["confirmation_class"] = tool_confirmation_class(tool)

    if tool_name == "get_tenant_summary":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            return _format_tenant_summary(result.data), tool_calls, [], None
        tool_calls[0]["ok"] = False
        return "Не удалось загрузить настройки.", tool_calls, [], None

    if tool_name == "get_knowledge":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            sources = extract_sources_from_knowledge(result.data)
            text = _kb_context_from_result(result)
            return text or result.message or "Ничего не найдено в базе знаний.", tool_calls, sources, None
        tool_calls[0]["ok"] = False
        return "Поиск в базе знаний не удался.", tool_calls, [], None

    if tool_name in ("hermes.setup_status", "hermes.health", "hermes.alerts", "calls.list", "billing.summary"):
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            if tool_name == "hermes.setup_status":
                data = result.data or {}
                from app.operator.tools.website_import_tool import _suggested_actions

                tool_calls[0]["suggested_actions"] = _suggested_actions(data.get("next_steps") or [])
                return _format_hermes_setup(data), tool_calls, [], None
            if tool_name == "hermes.health":
                return _format_hermes_health(result.data or {}), tool_calls, [], None
            if tool_name == "calls.list":
                return _format_calls_list(result.data or {}), tool_calls, [], None
            if tool_name == "billing.summary":
                return result.message or "Баланс недоступен.", tool_calls, [], None
            items = (result.data or {}).get("items") or []
            if not items:
                return "Свежих алертов нет — всё тихо.", tool_calls, [], None
            lines = ["Последние события офиса:"]
            for item in items[:8]:
                et = item.get("event_type") or item.get("code") or "event"
                msg = item.get("message_ru") or item.get("summary") or str(item.get("payload") or "")[:120]
                lines.append(f"• {et}: {msg}")
            return "\n".join(lines), tool_calls, [], None
        tool_calls[0]["ok"] = False
        return "Не удалось получить статус Hermes.", tool_calls, [], None

    if tool_name == "office.import_website":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            suggested = (result.data or {}).get("suggested_actions") or []
            if suggested:
                tool_calls[0]["suggested_actions"] = suggested
            return result.message or summary, tool_calls, [], None
        tool_calls[0]["ok"] = False
        msg = result.message if isinstance(result, ToolResult) else "Ошибка"
        return f"Не удалось импортировать сайт: {msg}", tool_calls, [], None

    if requires_confirmation(tool):
        pending = _pending_confirmation_dict(tool_name, params, summary)
        tool_calls[0]["pending"] = True
        reply = f"Готов выполнить: {summary}. Подтвердите действие кнопкой ниже."
        return reply, tool_calls, [], pending

    result = registry.run(db, ctx, tool_name, **params)
    if isinstance(result, ToolResult) and result.ok:
        tool_calls[0]["ok"] = True
        return result.message or summary, tool_calls, [], None
    tool_calls[0]["ok"] = False
    msg = result.message if isinstance(result, ToolResult) else "Ошибка"
    return f"Не удалось: {msg}", tool_calls, [], None


def _try_cabinet_llm_tools(
    db: Session,
    ctx: TenantContext,
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None] | None:
    provider = get_model_provider()
    if provider.name == "stub":
        return None

    tools = registry.list_openai_specs(names=list(CABINET_LLM_TOOLS))
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                f"Ты Hermes — ИИ-руководитель офиса DELNO для tenant {ctx.tenant_slug}. "
                "Владелец настраивает и управляет офисом голосом или текстом, как в чате с ассистентом. "
                "У тебя есть история этого диалога — опирайся на неё, не забывай прошлые шаги. "
                "Обязанности: (1) первый сетап — hermes.setup_status / phones.provision / флаги / KB; "
                "(2) health-watch — hermes.health и сразу сообщить о проблемах простым языком; "
                "(3) дирижирование — calls.dial/list, календарь, почта, ВКС, рассылка; "
                "(4) сайт компании — office.import_website / web.fetch / web.browse: "
                "МОЖЕШЬ заходить на публичные сайты, собирать текст в базу знаний и предлагать "
                "настройку коннекторов. Никогда не говори, что не умеешь открывать сайты — "
                "вызывай tool. "
                "(5) логины/пароли/доступы — сначала get_knowledge, не отвечай «нет данных» вслепую. "
                "Если сетап не завершён — предложи следующий шаг из checklist. "
                "Для изменений вызывай tools. Отвечай кратко по-русски."
            ),
        }
    ]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": message})
    completion = provider.chat_completion(
        messages=messages,
        tools=tools,
    )
    if not completion.get("ok"):
        return None

    try:
        choice_msg = completion["data"]["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None

    # Always meter the routing LLM turn (tools or text).
    _charge_llm_if_any(db, ctx, completion, channel="hermes")

    tool_calls_raw = choice_msg.get("tool_calls") or []
    if tool_calls_raw:
        first = tool_calls_raw[0]
        fn = first.get("function") or {}
        tool_name = str(fn.get("name") or "")
        params = _parse_tool_args(fn.get("arguments"))
        if tool_name:
            return _execute_cabinet_tool(db, ctx, tool_name, params)

    content = str(choice_msg.get("content") or "").strip()
    if content:
        return content, [{"tool": "llm", "ok": True, "provider": provider.name}], [], None
    return None


def _try_cabinet_setup(
    db: Session,
    ctx: TenantContext,
    message: str,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None] | None:
    intent = parse_setup_intent(message)
    if not intent:
        return None

    tool_name = str(intent["tool"])
    params = dict(intent.get("params") or {})
    return _execute_cabinet_tool(db, ctx, tool_name, params)


def _fallback_reply(kb_context: str) -> str:
    if kb_context:
        return kb_context[:2000]
    return (
        "Я DELNO — ИИ-сотрудник. Могу ответить по услугам и тарифам из базы знаний "
        "или подсказать, как оставить заявку на сайте."
    )


def _generate_reply(
    db: Session,
    ctx: TenantContext,
    message: str,
    *,
    channel: str = "web",
    attachments: dict[str, Any] | None = None,
    conversation_id: uuid.UUID | None = None,
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """KB search + optional LLM; cabinet channel enables live setup intents."""
    from app.services.operator_attachments import build_user_content

    tool_calls: list[dict[str, Any]] = []
    kb_context = ""
    sources: list[dict[str, Any]] = []
    onboarding = channel == "onboarding"
    cabinet = channel in ("cabinet", "operator", "hermes")
    widget = channel == "widget"
    has_attachments = bool(attachments and (attachments.get("items") or []))
    history: list[dict[str, str]] = []
    if conversation_id is not None:
        history = _conversation_history_for_llm(
            db,
            tenant_id=ctx.tenant_id,
            conversation_id=conversation_id,
            limit=24,
        )

    if onboarding and not has_attachments:
        from app.services.onboarding_website import try_onboarding_url_ingest
        from app.services.onboarding_summary import try_onboarding_summary_reply

        url_ingest = try_onboarding_url_ingest(db, ctx, message)
        if url_ingest:
            return (
                url_ingest["reply"],
                url_ingest.get("tool_calls") or [],
                url_ingest.get("sources") or [],
                None,
                None,
            )

        summary_reply = try_onboarding_summary_reply(db, ctx, message)
        if summary_reply:
            return (
                summary_reply["reply"],
                summary_reply.get("tool_calls") or [],
                summary_reply.get("sources") or [],
                None,
                None,
            )

    if cabinet and not has_attachments:
        from app.services.hermes_guide import coach_reply

        secret_form = _try_secret_form_turn(message)
        if secret_form:
            return secret_form

        # Phone/setup coach first — avoid dumping generic setup tool text or KB FAQ
        guided = coach_reply(db, ctx, message)
        if guided:
            tool_calls = list(guided.get("tool_calls") or [])
            suggested = guided.get("suggested_actions")
            if suggested and tool_calls:
                tool_calls[0] = dict(tool_calls[0])
                tool_calls[0]["suggested_actions"] = suggested
            elif suggested:
                tool_calls.append({"tool": "hermes.guide", "ok": True, "suggested_actions": suggested})
            # pull suggested_actions nested in tool_calls (e.g. sip.probe)
            return (
                guided["reply"],
                tool_calls,
                [],
                None,
                guided.get("pending_credential_form"),
            )

        # Read-only KB lookup for «какой пароль» — after paste/form handling
        cred = _try_kb_credential_lookup(db, ctx, message)
        if cred:
            return (*cred, None)

        setup = _try_cabinet_setup(db, ctx, message)
        if setup:
            return (*setup, None)
        llm_tools = _try_cabinet_llm_tools(db, ctx, message, history=history)
        if llm_tools:
            return (*llm_tools, None)

    kb_query = message
    if has_attachments and attachments.get("text_context"):
        kb_query = f"{message}\n{attachments.get('text_context')}"[:500]
    knowledge = registry.run(db, ctx, "get_knowledge", query=kb_query or message)
    if isinstance(knowledge, ToolResult):
        tool_calls.append({"tool": "get_knowledge", "ok": knowledge.ok})
        if knowledge.ok:
            kb_context = _kb_context_from_result(knowledge)
            sources = extract_sources_from_knowledge(knowledge.data)

    if has_attachments:
        tool_calls.append(
            {
                "tool": "attachments",
                "ok": True,
                "count": len(attachments.get("items") or []),
                "kinds": [i.get("kind") for i in (attachments.get("items") or [])],
            }
        )

    user_content = build_user_content(message, attachments or {})
    # Vision needs a multimodal-capable model
    vision = bool(attachments and attachments.get("vision_parts"))
    model_override = "gpt-4o-mini" if widget or vision else None

    provider = get_model_provider()
    llm_messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": _system_prompt(
                ctx,
                kb_context,
                cabinet=cabinet,
                onboarding=onboarding,
                widget=widget,
            )
            + (
                "\nПользователь может прикладывать фото и файлы. "
                "Для изображений опиши увиденное и предложи конкретное действие в офисе."
                if has_attachments
                else ""
            ),
        }
    ]
    if history and not widget:
        llm_messages.extend(history)
    llm_messages.append({"role": "user", "content": user_content})
    completion = provider.chat_completion(
        messages=llm_messages,
        model=model_override,
        max_tokens=450 if vision else (220 if widget else None),
    )

    if completion.get("ok"):
        try:
            reply = str(completion["data"]["choices"][0]["message"]["content"]).strip()
            provider_name = str(completion.get("provider") or "")
            stub_echo = provider_name == "stub" and reply.startswith("[stub]")
            if reply and not stub_echo:
                _charge_llm_if_any(db, ctx, completion, channel=channel)
                tool_calls.append({"tool": "llm", "ok": True, "provider": provider_name})
                return reply, tool_calls, sources, None, None
            if stub_echo:
                tool_calls.append({"tool": "llm", "ok": False, "provider": provider_name, "error": "stub_echo"})
        except (KeyError, IndexError, TypeError):
            tool_calls.append({"tool": "llm", "ok": False, "error": "invalid_completion_shape"})
    else:
        tool_calls.append(
            {
                "tool": "llm",
                "ok": False,
                "provider": str(completion.get("provider") or provider.name),
                "error": str(completion.get("error") or "llm_failed"),
            }
        )

    # Hermes cabinet: never dump raw KB FAQ as "answer" when LLM is geo-blocked
    if cabinet:
        from app.services.hermes_guide import coach_reply, llm_unavailable_reply

        guided = coach_reply(db, ctx, message)
        if guided:
            return (
                guided["reply"],
                (guided.get("tool_calls") or []) + tool_calls,
                [],
                None,
                guided.get("pending_credential_form"),
            )
        return llm_unavailable_reply(message), tool_calls, [], None, None

    if any(word in message.lower() for word in ("заявк", "оставить", "позвон", "связ")):
        return (
            "Могу подсказать по услугам из базы знаний. Чтобы оформить заявку — используйте форму на сайте "
            "или напишите имя и телефон, и менеджер свяжется с вами.",
            tool_calls,
            sources,
            None,
            None,
        )

    return _fallback_reply(kb_context), tool_calls, sources, None, None


def execute_confirmed_tool(
    db: Session,
    ctx: TenantContext,
    *,
    tool_name: str,
    params: dict[str, Any],
) -> ToolResult | PendingConfirmation:
    """Run a critical tool after explicit user confirmation."""
    result = registry.run(db, ctx, tool_name, **params)
    write_audit(
        db,
        ctx,
        action="operator.confirm_tool",
        resource=tool_name,
        new_value={"params": params, "confirmed": True},
        result="ok" if isinstance(result, ToolResult) and result.ok else "pending",
    )
    db.commit()
    return result
