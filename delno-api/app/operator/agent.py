"""Operator LLM loop — read-only KB + cabinet live setup."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.operator.setup_intent import parse_setup_intent
from app.operator.tools.registry import PendingConfirmation, ToolResult, registry
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.model_provider import get_model_provider
from app.services.provenance import extract_sources_from_knowledge


def run_operator_turn(
    db: Session,
    ctx: TenantContext,
    *,
    message: str,
    channel: str = "web",
    conversation_id: uuid.UUID | None = None,
    input_modality: str = "text",
) -> dict[str, Any]:
    """
    Single operator turn. Text and voice (post-STT) use the same path.
    Voice output (TTS) is handled by the client or a future /operator/voice route.
    """
    try:
        conversation = _get_or_create_conversation(db, ctx, channel, conversation_id)
        db.add(
            Message(
                tenant_id=ctx.tenant_id,
                conversation_id=conversation.id,
                role="user",
                body=message,
                meta={"modality": input_modality},
            )
        )
        db.flush()

        reply, tool_calls, sources, pending = _generate_reply(
            db, ctx, message, channel=channel
        )

        meta: dict[str, Any] = {"tool_calls": tool_calls, "sources": sources}
        if pending:
            meta["pending_confirmation"] = pending

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
        db.commit()

        return {
            "conversation_id": str(conversation.id),
            "reply": reply,
            "tool_calls": tool_calls,
            "sources": sources,
            "modality": input_modality,
            "pending_confirmation": pending,
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
        db.commit()
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


def _system_prompt(ctx: TenantContext, kb_context: str, *, cabinet: bool = False) -> str:
    base = (
        f"Ты DELNO — ИИ-сотрудник компании (tenant: {ctx.tenant_slug}). "
        "Отвечай кратко по-русски. Используй только факты из базы знаний ниже. "
        "Если данных недостаточно — честно скажи об этом и предложи оставить заявку на сайте. "
        "Не выдумывай цены, условия и действия. Не запрашивай tenant_id и не выполняй массовые операции."
    )
    if cabinet:
        base += (
            " Ты в кабинете владельца: помогай настраивать DELNO на лету "
            "(база знаний, часы работы, флаги каналов). Изменения применяются только после подтверждения."
        )
    if kb_context:
        return f"{base}\n\n--- База знаний ---\n{kb_context}"
    return base


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
    summary = str(intent.get("summary") or tool_name)
    tool_calls: list[dict[str, Any]] = [{"tool": tool_name, "ok": None, "pending": True}]

    tool = registry.get(tool_name)
    if not tool:
        return (
            f"Не удалось выполнить «{summary}»: инструмент недоступен.",
            tool_calls,
            [],
            None,
        )

    if tool_name == "get_tenant_summary":
        result = registry.run(db, ctx, tool_name, **params)
        if isinstance(result, ToolResult) and result.ok:
            tool_calls[0]["ok"] = True
            return _format_tenant_summary(result.data), tool_calls, [], None
        tool_calls[0]["ok"] = False
        return "Не удалось загрузить настройки.", tool_calls, [], None

    if getattr(tool, "critical_write", False):
        pending = _pending_confirmation_dict(tool_name, params, summary)
        reply = f"Готов выполнить: {summary}. Подтвердите действие кнопкой ниже."
        return reply, tool_calls, [], pending

    result = registry.run(db, ctx, tool_name, **params)
    if isinstance(result, ToolResult) and result.ok:
        tool_calls[0]["ok"] = True
        return result.message or summary, tool_calls, [], None
    tool_calls[0]["ok"] = False
    msg = result.message if isinstance(result, ToolResult) else "Ошибка"
    return f"Не удалось: {msg}", tool_calls, [], None


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
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None]:
    """KB search + optional LLM; cabinet channel enables live setup intents."""
    tool_calls: list[dict[str, Any]] = []
    kb_context = ""
    sources: list[dict[str, Any]] = []
    cabinet = channel in ("cabinet", "operator")

    if cabinet:
        setup = _try_cabinet_setup(db, ctx, message)
        if setup:
            return setup

    knowledge = registry.run(db, ctx, "get_knowledge", query=message)
    if isinstance(knowledge, ToolResult):
        tool_calls.append({"tool": "get_knowledge", "ok": knowledge.ok})
        if knowledge.ok:
            kb_context = _kb_context_from_result(knowledge)
            sources = extract_sources_from_knowledge(knowledge.data)

    provider = get_model_provider()
    completion = provider.chat_completion(
        messages=[
            {"role": "system", "content": _system_prompt(ctx, kb_context, cabinet=cabinet)},
            {"role": "user", "content": message},
        ]
    )

    if completion.get("ok"):
        try:
            reply = str(completion["data"]["choices"][0]["message"]["content"]).strip()
            provider_name = str(completion.get("provider") or "")
            stub_echo = provider_name == "stub" and reply.startswith("[stub]")
            if reply and not stub_echo:
                tool_calls.append({"tool": "llm", "ok": True, "provider": provider_name})
                return reply, tool_calls, sources, None
            if stub_echo:
                tool_calls.append({"tool": "llm", "ok": False, "provider": provider_name, "error": "stub_echo"})
        except (KeyError, IndexError, TypeError):
            tool_calls.append({"tool": "llm", "ok": False, "error": "invalid_completion_shape"})

    if any(word in message.lower() for word in ("заявк", "оставить", "позвон", "связ")):
        return (
            "Могу подсказать по услугам из базы знаний. Чтобы оформить заявку — используйте форму на сайте "
            "или напишите имя и телефон, и менеджер свяжется с вами.",
            tool_calls,
            sources,
            None,
        )

    return _fallback_reply(kb_context), tool_calls, sources, None


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
