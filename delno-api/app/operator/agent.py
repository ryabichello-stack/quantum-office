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
from app.core.config import get_settings
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
    "hermes.capabilities",
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
    # Telephony secretary script + in-call tools
    "telephony.script_get",
    "telephony.script_propose",
    "telephony.script_save",
    "telephony.tools_set",
    # Cloud disks
    "files.cloud_status",
    "files.cloud_list",
    "credentials.open_form",
    # Office connectors
    "suggest_calendar_slots",
    "send_mail_draft",
    "list_files",
    "create_conference",
    # Media
    "generate_image",
    # Hermes web browser
    "web.search",
    "web.fetch",
    "web.browse",
    "office.import_website",
    "billing.summary",
)

HERMES_AGENT_SYSTEM = (
    "Ты Hermes — автономный ИИ-агент офиса DELNO для этого tenant. "
    "Владелец формулирует цель обычным языком. Ты сам понимаешь задачу, "
    "сам составляешь план и СРАЗУ выполняешь его через tools: "
    "tool → результат → следующий tool → … → только потом финальный ответ.\n"
    "Критично: не рассказывай «сейчас схожу / сейчас найду / сейчас сделаю». "
    "Если нужен интернет, статус, файлы, телефония — СНАЧАЛА вызови tool, "
    "без tool не обещай действие. Финальный текст — только после фактов из tools "
    "или если tools реально не нужны (приветствие, уточняющий вопрос).\n"
    "Не жди волшебных фраз и не подменяй задачу шаблонным статусом SIP/сетапа.\n"
    "Каталог tools (выбираешь сам по смыслу задачи):\n"
    "• web.search / web.fetch / web.browse — открытый интернет;\n"
    "• get_knowledge / upload_knowledge_snippet / office.import_website — "
    "только материалы ЭТОГО tenant (локальная база), не замена интернету;\n"
    "• hermes.capabilities — проверь реальные возможности перед онбордингом и задачами;\n"
    "• hermes.setup_status / health / alerts — состояние офиса;\n"
    "• phones.* / calls.* / telephony.script_* / telephony.tools_set — телефония Ava;\n"
    "• files.cloud_* / credentials.open_form — облака и секреты "
    "(SIP: mango_sip; диски: files_yadisk|mailru|gdrive|onedrive; Google/OneDrive с согласием);\n"
    "• suggest_calendar_slots / send_mail_draft / create_conference / list_files — офис;\n"
    "• generate_image — создай картинку/мокап/обложку по текстовому промпту "
    "(НЕ отказывайся «я не умею рисовать» — сразу вызови tool);\n"
    "• billing.summary — баланс.\n"
    "Правила:\n"
    "• Секреты в чат не проси — только credentials.open_form.\n"
    "• Критичные записи система сама попросит подтвердить.\n"
    "• Ошибки tools не скрывай — говори что упало.\n"
    "• Отвечай по-русски, по делу, со ссылками если брал из сети."
)

_INTENT_NARRATION_MARKERS = (
    "сейчас схожу",
    "сейчас найду",
    "сейчас провер",
    "сейчас сделаю",
    "сейчас соберу",
    "сейчас поищу",
    "сейчас открою",
    "сейчас зайду",
    "я сейчас",
    "давай найду",
    "пойду ",
    "схожу ",
    "начну ",
    "let me ",
    "i'll ",
    "i will ",
)


def _looks_like_intent_narration(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _INTENT_NARRATION_MARKERS)

def _hermes_debug_failures() -> bool:
    try:
        return bool(get_settings().hermes_debug_failures)
    except Exception:  # noqa: BLE001
        return True


def _cabinet_agent_max_rounds() -> int:
    """Hard safety rail (cf. LangGraph recursion_limit). Soft-stop is primary."""
    try:
        n = int(get_settings().hermes_agent_max_rounds)
    except Exception:  # noqa: BLE001
        n = 25
    return max(4, min(n, 200))


def _cabinet_agent_no_progress_limit() -> int:
    try:
        n = int(get_settings().hermes_agent_no_progress_limit)
    except Exception:  # noqa: BLE001
        n = 3
    return max(2, min(n, 20))


def _cabinet_agent_max_tokens() -> int:
    """0 = unlimited. Counts prompt+completion across the whole agent turn."""
    try:
        n = int(get_settings().hermes_agent_max_tokens)
    except Exception:  # noqa: BLE001
        n = 100_000
    return max(0, min(n, 2_000_000))


def _tool_call_fingerprint(tool_name: str, params: dict[str, Any]) -> str:
    try:
        blob = json.dumps(
            {"n": tool_name, "p": params},
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
    except Exception:  # noqa: BLE001
        blob = f"{tool_name}:{params!r}"
    return blob


def _completion_token_total(completion: dict[str, Any]) -> int:
    usage = completion.get("usage") if isinstance(completion.get("usage"), dict) else {}
    prompt = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total = int(usage.get("total_tokens") or 0)
    return total or (prompt + completion_tokens)


def _format_debug_failures(
    *,
    tools: list[dict[str, Any]] | None = None,
    llm_error: str | None = None,
) -> str:
    """Human-readable failure trail for cabinet debug replies."""
    lines: list[str] = []
    if llm_error:
        lines.append(f"LLM: {llm_error}")
    for t in tools or []:
        if not isinstance(t, dict):
            continue
        name = str(t.get("tool") or "?")
        if t.get("blocked"):
            lines.append(f"{name}: заблокирован ({t.get('error') or 'policy'})")
            continue
        if t.get("pending"):
            continue
        if t.get("ok") is True and name != "llm":
            continue
        if name == "llm" and t.get("ok") is True:
            continue
        detail = (
            t.get("detail")
            or t.get("error")
            or t.get("message")
            or ("fail" if t.get("ok") is False else None)
        )
        if detail:
            lines.append(f"{name}: {detail}")
    if not lines:
        return ""
    return "\n\n— отладка (сбои) —\n" + "\n".join(f"• {x}" for x in lines)


def _with_debug_failures(
    reply: str,
    *,
    tools: list[dict[str, Any]] | None = None,
    llm_error: str | None = None,
) -> str:
    if not _hermes_debug_failures():
        return reply
    return (reply or "") + _format_debug_failures(tools=tools, llm_error=llm_error)


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
        pending_download: dict[str, Any] | None = None
        for tc in tool_calls or []:
            if not isinstance(tc, dict):
                continue
            if not suggested_actions and isinstance(tc.get("suggested_actions"), list):
                suggested_actions = [
                    a
                    for a in tc["suggested_actions"]
                    if isinstance(a, dict) and a.get("title") and a.get("text")
                ]
            if not pending_download and isinstance(tc.get("pending_download"), dict):
                pending_download = tc["pending_download"]

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
        if pending_download:
            meta["pending_download"] = {
                "filename": pending_download.get("filename"),
                "title": pending_download.get("title"),
            }

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
            "pending_download": pending_download,
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
        base += " " + HERMES_AGENT_SYSTEM
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
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    summary = _tool_summary(tool_name, params)
    tool_calls: list[dict[str, Any]] = [{"tool": tool_name, "ok": None}]

    tool = registry.get(tool_name)
    if not tool:
        tool_calls[0]["ok"] = False
        return f"Инструмент «{tool_name}» недоступен.", tool_calls, [], None, None

    tool_calls[0]["confirmation_class"] = tool_confirmation_class(tool)

    if tool_name == "get_tenant_summary":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            return _format_tenant_summary(result.data), tool_calls, [], None, None
        tool_calls[0]["ok"] = False
        return "Не удалось загрузить настройки.", tool_calls, [], None, None

    if tool_name == "get_knowledge":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            sources = extract_sources_from_knowledge(result.data)
            text = _kb_context_from_result(result)
            return text or result.message or "Ничего не найдено в базе знаний.", tool_calls, sources, None, None
        tool_calls[0]["ok"] = False
        return "Поиск в базе знаний не удался.", tool_calls, [], None, None

    if tool_name in ("hermes.setup_status", "hermes.health", "hermes.alerts", "calls.list", "billing.summary"):
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            if tool_name == "hermes.setup_status":
                data = result.data or {}
                from app.operator.tools.website_import_tool import _suggested_actions

                tool_calls[0]["suggested_actions"] = _suggested_actions(data.get("next_steps") or [])
                return _format_hermes_setup(data), tool_calls, [], None, None
            if tool_name == "hermes.health":
                return _format_hermes_health(result.data or {}), tool_calls, [], None, None
            if tool_name == "calls.list":
                return _format_calls_list(result.data or {}), tool_calls, [], None, None
            if tool_name == "billing.summary":
                return result.message or "Баланс недоступен.", tool_calls, [], None, None
            items = (result.data or {}).get("items") or []
            if not items:
                return "Свежих алертов нет — всё тихо.", tool_calls, [], None, None
            lines = ["Последние события офиса:"]
            for item in items[:8]:
                et = item.get("event_type") or item.get("code") or "event"
                msg = item.get("message_ru") or item.get("summary") or str(item.get("payload") or "")[:120]
                lines.append(f"• {et}: {msg}")
            return "\n".join(lines), tool_calls, [], None, None
        tool_calls[0]["ok"] = False
        return "Не удалось получить статус Hermes.", tool_calls, [], None, None

    if tool_name == "office.import_website":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            suggested = (result.data or {}).get("suggested_actions") or []
            if suggested:
                tool_calls[0]["suggested_actions"] = suggested
            return result.message or summary, tool_calls, [], None, None
        tool_calls[0]["ok"] = False
        msg = result.message if isinstance(result, ToolResult) else "Ошибка"
        return f"Не удалось импортировать сайт: {msg}", tool_calls, [], None, None

    if tool_name == "credentials.open_form":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            form = (result.data or {}).get("pending_credential_form")
            return result.message or summary, tool_calls, [], None, form if isinstance(form, dict) else None
        tool_calls[0]["ok"] = False
        return "Не удалось открыть форму.", tool_calls, [], None, None

    if tool_name == "generate_image":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            data = result.data or {}
            md = data.get("markdown") or ""
            caption = f"Готово — сгенерировал изображение по запросу: «{(params.get('prompt') or '')[:120]}»."
            reply = f"{caption}\n\n{md}".strip() if md else caption
            return reply, tool_calls, [], None, None
        tool_calls[0]["ok"] = False
        msg = result.message if isinstance(result, ToolResult) else "Ошибка"
        return f"Не удалось сгенерировать изображение: {msg}", tool_calls, [], None, None

    if tool_name in (
        "telephony.script_get",
        "telephony.script_propose",
        "telephony.script_save",
        "telephony.tools_set",
        "files.cloud_status",
        "files.cloud_list",
    ):
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            return result.message or summary, tool_calls, [], None, None
        tool_calls[0]["ok"] = False
        msg = result.message if isinstance(result, ToolResult) else "Ошибка"
        return msg or f"Не удалось: {tool_name}", tool_calls, [], None, None

    if requires_confirmation(tool):
        pending = _pending_confirmation_dict(tool_name, params, summary)
        tool_calls[0]["pending"] = True
        reply = f"Готов выполнить: {summary}. Подтвердите действие кнопкой ниже."
        return reply, tool_calls, [], pending, None

    result = registry.run(db, ctx, tool_name, **params)
    if isinstance(result, ToolResult) and result.ok:
        tool_calls[0]["ok"] = True
        form = (result.data or {}).get("pending_credential_form") if isinstance(result.data, dict) else None
        return result.message or summary, tool_calls, [], None, form if isinstance(form, dict) else None
    tool_calls[0]["ok"] = False
    msg = result.message if isinstance(result, ToolResult) else "Ошибка"
    return f"Не удалось: {msg}", tool_calls, [], None, None


def _tool_result_for_llm(result: ToolResult | PendingConfirmation | Any) -> str:
    if isinstance(result, PendingConfirmation):
        return json.dumps(
            {
                "ok": False,
                "needs_confirmation": True,
                "tool": result.tool_name,
                "summary": result.summary,
            },
            ensure_ascii=False,
        )
    if isinstance(result, ToolResult):
        payload: dict[str, Any] = {"ok": result.ok, "message": (result.message or "")[:4000]}
        data = result.data if isinstance(result.data, dict) else {}
        # Prefer compact structured bits for web / KB so the model can chain.
        if "connectors" in data:
            payload["connectors"] = data.get("connectors")
        if "tools" in data:
            payload["tools"] = data.get("tools")
        if "missing" in data:
            payload["missing"] = data.get("missing")
        if "items" in data:
            payload["items"] = data.get("items")
        if "query" in data:
            payload["query"] = data.get("query")
        if "url" in data:
            payload["url"] = data.get("url")
        if "title" in data:
            payload["title"] = data.get("title")
        if "text" in data and isinstance(data.get("text"), str):
            payload["text"] = data["text"][:6000]
        if "chars" in data:
            payload["chars"] = data.get("chars")
        if "pending_credential_form" in data:
            payload["pending_credential_form"] = True
        if "markdown" in data:
            payload["markdown"] = data.get("markdown")
        if "image_url" in data:
            payload["image_url"] = data.get("image_url")
        if "image_data_url" in data and isinstance(data.get("image_data_url"), str):
            # Keep LLM payload short — full data-URL is for the user-facing reply path.
            payload["image_data_url_len"] = len(data["image_data_url"])
            payload["has_image"] = True
        return json.dumps(payload, ensure_ascii=False)[:9000]
    return json.dumps({"ok": False, "error": "unknown_tool_result"}, ensure_ascii=False)


def _try_cabinet_llm_tools(
    db: Session,
    ctx: TenantContext,
    message: str,
    *,
    history: list[dict[str, str]] | None = None,
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
] | None:
    """
    Agent loop stop policy (normal systems):
      1) soft-stop — model returns text, no tool_calls (primary)
      2) no-progress — identical tool+args repeated N times
      3) token budget — optional per-turn ceiling
      4) max_rounds — hard safety rail only
    """
    provider = get_model_provider()
    if provider.name == "stub":
        err = "model_provider=stub (нет OPENAI_API_KEY / MODEL_PROVIDER)"
        reply = _with_debug_failures(
            "Сейчас LLM недоступен (stub) — не могу сам выбирать tools. "
            "Проверьте OPENAI_API_KEY / proxy на api.",
            tools=[{"tool": "llm", "ok": False, "error": err}],
            llm_error=err,
        )
        return reply, [{"tool": "llm", "ok": False, "error": err}], [], None, None

    # App lifespan registers tools; keep a safety net for workers/scripts.
    if not registry.list_catalog():
        from app.operator.tools import register_builtin_tools

        register_builtin_tools()

    tools = registry.list_openai_specs(names=list(CABINET_LLM_TOOLS))
    if not tools:
        err = "cabinet_tools_empty"
        reply = _with_debug_failures(
            "Каталог tools пуст — агент не может действовать. Проверьте register_builtin_tools.",
            tools=[{"tool": "llm", "ok": False, "error": err}],
            llm_error=err,
        )
        return reply, [{"tool": "llm", "ok": False, "error": err}], [], None, None
    system = f"{HERMES_AGENT_SYSTEM} Tenant: {ctx.tenant_slug}."
    if _hermes_debug_failures():
        system += " Режим отладки: при ok=false у tool назови ошибку владельцу."
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": message})

    collected_tools: list[dict[str, Any]] = []
    sources: list[dict[str, Any]] = []
    pending_form: dict[str, Any] | None = None
    ran_any_tool = False
    tokens_used = 0
    last_fingerprint = ""
    same_fingerprint_streak = 0
    force_tools = False
    narration_nudge_used = False

    max_rounds = _cabinet_agent_max_rounds()
    no_progress_limit = _cabinet_agent_no_progress_limit()
    max_tokens = _cabinet_agent_max_tokens()

    for _round in range(max_rounds):
        if max_tokens and tokens_used >= max_tokens:
            reply = (
                f"Остановился: исчерпан бюджет токенов на этот ход "
                f"({tokens_used}/{max_tokens}). "
                "Сформулируйте цель уже или продолжите отдельным сообщением."
            )
            return (
                _with_debug_failures(reply, tools=collected_tools, llm_error="token_budget"),
                collected_tools,
                sources,
                None,
                pending_form,
            )

        completion = provider.chat_completion(
            messages=messages,
            tools=tools,
            tool_choice="required" if force_tools else "auto",
        )
        force_tools = False
        if not completion.get("ok"):
            err = str(completion.get("error") or "llm_failed")
            reply = _with_debug_failures(
                (
                    f"Не удалось вызвать модель ({err}). "
                    "Без LLM не выбираю tools сам — повторите или проверьте proxy/ключ."
                    if not ran_any_tool
                    else f"Модель упала после инструментов ({err}). Ниже — что успело отработать."
                ),
                tools=collected_tools,
                llm_error=err,
            )
            collected_tools.append({"tool": "llm", "ok": False, "error": err})
            return reply, collected_tools, sources, None, pending_form

        try:
            choice_msg = completion["data"]["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            err = "empty_or_malformed_llm_response"
            reply = _with_debug_failures(
                "Модель вернула пустой/битый ответ.",
                tools=collected_tools,
                llm_error=err,
            )
            collected_tools.append({"tool": "llm", "ok": False, "error": err})
            return reply, collected_tools, sources, None, pending_form

        tokens_used += _completion_token_total(completion)
        _charge_llm_if_any(db, ctx, completion, channel="hermes")

        tool_calls_raw = choice_msg.get("tool_calls") or []
        if not tool_calls_raw:
            # Soft-stop: model finished on its own — unless it only narrated intent.
            content = str(choice_msg.get("content") or "").strip()
            if (
                content
                and not ran_any_tool
                and not narration_nudge_used
                and _looks_like_intent_narration(content)
            ):
                narration_nudge_used = True
                messages.append({"role": "assistant", "content": content})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Не описывай план словами. Сразу вызови нужные tools "
                            "(например web.search / web.fetch) и только потом ответь по фактам."
                        ),
                    }
                )
                force_tools = True
                continue
            if content:
                meta = [
                    {
                        "tool": "llm",
                        "ok": True,
                        "provider": provider.name,
                        "rounds": _round + 1,
                        "tokens_used": tokens_used,
                        "stop": "soft",
                    }
                ]
                out_tools = collected_tools or meta
                return (
                    _with_debug_failures(content, tools=out_tools),
                    out_tools,
                    sources,
                    None,
                    pending_form,
                )
            if ran_any_tool:
                last = collected_tools[-1] if collected_tools else {}
                reply = str(
                    last.get("message")
                    or "Инструменты отработали, но модель не сформулировала ответ."
                )
                return (
                    _with_debug_failures(reply, tools=collected_tools, llm_error="no_final_text"),
                    collected_tools,
                    sources,
                    None,
                    pending_form,
                )
            return None

        messages.append(
            {
                "role": "assistant",
                "content": choice_msg.get("content") or None,
                "tool_calls": tool_calls_raw,
            }
        )

        for raw_tc in tool_calls_raw:
            fn = raw_tc.get("function") or {}
            tool_name = registry.resolve_openai_name(str(fn.get("name") or ""))
            params = _parse_tool_args(fn.get("arguments"))
            tc_id = str(raw_tc.get("id") or f"call_{tool_name}_{_round}")
            if not tool_name:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps({"ok": False, "error": "empty_tool_name"}),
                    }
                )
                continue

            fp = _tool_call_fingerprint(tool_name, params)
            if fp == last_fingerprint:
                same_fingerprint_streak += 1
            else:
                last_fingerprint = fp
                same_fingerprint_streak = 1
            if same_fingerprint_streak >= no_progress_limit:
                entry = {
                    "tool": tool_name,
                    "ok": False,
                    "params": params,
                    "error": "no_progress",
                    "detail": f"repeated×{same_fingerprint_streak}",
                }
                collected_tools.append(entry)
                reply = (
                    f"Остановился: один и тот же шаг `{tool_name}` повторяется "
                    f"без прогресса ({same_fingerprint_streak}×). "
                    "Уточните задачу или дайте другой вход — иначе буду крутиться."
                )
                return (
                    _with_debug_failures(reply, tools=collected_tools, llm_error="no_progress"),
                    collected_tools,
                    sources,
                    None,
                    pending_form,
                )

            tool = registry.get(tool_name)
            entry = {"tool": tool_name, "ok": False, "params": params}
            if tool is None:
                entry["error"] = "unknown_tool"
                collected_tools.append(entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps({"ok": False, "error": f"unknown tool {tool_name}"}),
                    }
                )
                continue

            if requires_confirmation(tool):
                summary = _tool_summary(tool_name, params)
                pending = _pending_confirmation_dict(tool_name, params, summary)
                entry["pending"] = True
                entry["ok"] = True
                collected_tools.append(entry)
                reply = f"Готов выполнить: {summary}. Подтвердите действие кнопкой ниже."
                return reply, collected_tools, sources, pending, pending_form

            result = registry.run(db, ctx, tool_name, **params)
            ran_any_tool = True
            if isinstance(result, ToolResult):
                entry["ok"] = result.ok
                entry["message"] = (result.message or "")[:500]
                if isinstance(result.data, dict):
                    if not result.ok:
                        entry["error"] = str(
                            result.data.get("error") or result.message or "tool_failed"
                        )[:300]
                        if result.data.get("detail"):
                            entry["detail"] = str(result.data.get("detail"))[:300]
                    form = result.data.get("pending_credential_form")
                    if isinstance(form, dict):
                        pending_form = form
                        collected_tools.append(entry)
                        return (
                            _with_debug_failures(
                                result.message or "Откройте форму ниже и сохраните данные.",
                                tools=collected_tools,
                            ),
                            collected_tools,
                            sources,
                            None,
                            pending_form,
                        )
                    if tool_name == "get_knowledge" and result.ok:
                        sources = extract_sources_from_knowledge(result.data) or sources
                elif not result.ok:
                    entry["error"] = (result.message or "tool_failed")[:300]
                collected_tools.append(entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": _tool_result_for_llm(result),
                    }
                )
            else:
                entry["ok"] = False
                entry["error"] = "unexpected_result"
                collected_tools.append(entry)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": _tool_result_for_llm(result),
                    }
                )

    # Hard ceiling: ask for a final answer without more tools.
    completion = provider.chat_completion(messages=messages, tools=None, max_tokens=900)
    if completion.get("ok"):
        tokens_used += _completion_token_total(completion)
        _charge_llm_if_any(db, ctx, completion, channel="hermes")
        try:
            content = str(completion["data"]["choices"][0]["message"].get("content") or "").strip()
        except (KeyError, IndexError, TypeError):
            content = ""
        if content:
            return (
                _with_debug_failures(content, tools=collected_tools),
                collected_tools,
                sources,
                None,
                pending_form,
            )

    if collected_tools:
        last = collected_tools[-1]
        reply = str(
            last.get("message")
            or (
                f"Достигнут потолок раундов ({max_rounds}) — вот последний результат. "
                "Можно продолжить следующим сообщением."
            )
        )
        return (
            _with_debug_failures(reply, tools=collected_tools, llm_error="max_rounds"),
            collected_tools,
            sources,
            None,
            pending_form,
        )
    return None


def _try_cabinet_setup(
    db: Session,
    ctx: TenantContext,
    message: str,
) -> tuple[
    str,
    list[dict[str, Any]],
    list[dict[str, Any]],
    dict[str, Any] | None,
    dict[str, Any] | None,
] | None:
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

    skip_kb = False
    if cabinet and not has_attachments:
        from app.services.hermes_guide import coach_reply

        # 1) Secrets never go through LLM as chat text
        secret_form = _try_secret_form_turn(message)
        if secret_form:
            return secret_form

        # 2) Agent-first: LLM chooses tools from the full catalog (no keyword scripts)
        llm_tools = _try_cabinet_llm_tools(db, ctx, message, history=history)
        if llm_tools:
            return llm_tools

        # 3) Optional thin keyword intents only if LLM unavailable
        setup = _try_cabinet_setup(db, ctx, message)
        if setup:
            return setup

        cred = _try_kb_credential_lookup(db, ctx, message)
        if cred:
            return (*cred, None)

        # 4) Deterministic coach only as offline/geo-block fallback
        guided = coach_reply(db, ctx, message)
        if guided:
            tool_calls = list(guided.get("tool_calls") or [])
            suggested = guided.get("suggested_actions")
            if suggested and tool_calls:
                tool_calls[0] = dict(tool_calls[0])
                tool_calls[0]["suggested_actions"] = suggested
            elif suggested:
                tool_calls.append({"tool": "hermes.guide", "ok": True, "suggested_actions": suggested})
            if guided.get("pending_download") and tool_calls:
                tool_calls = list(tool_calls)
                if not any(isinstance(t, dict) and t.get("pending_download") for t in tool_calls):
                    tool_calls.append(
                        {
                            "tool": "hermes.templates.download",
                            "ok": True,
                            "pending_download": guided["pending_download"],
                        }
                    )
            return (
                guided["reply"],
                tool_calls,
                [],
                None,
                guided.get("pending_credential_form"),
            )

        # Hermes office chat: don't RAG-dump vault docs for ordinary dialogue
        skip_kb = True

    kb_query = message
    if has_attachments and attachments.get("text_context"):
        kb_query = f"{message}\n{attachments.get('text_context')}"[:500]
    if not skip_kb:
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
