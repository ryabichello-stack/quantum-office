import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation, Message
from app.operator.tools.registry import PendingConfirmation, ToolResult, registry
from app.services.audit import write_audit


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

    reply, tool_calls = _generate_reply(db, ctx, message)

    db.add(
        Message(
            tenant_id=ctx.tenant_id,
            conversation_id=conversation.id,
            role="assistant",
            body=reply,
            meta={"tool_calls": tool_calls},
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
        "modality": input_modality,
    }


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


def _generate_reply(db: Session, ctx: TenantContext, message: str) -> tuple[str, list[dict[str, Any]]]:
    """
    MVP: keyword routing to tools. Replaced by LLM + tool loop without API changes.
    """
    lowered = message.lower()
    tool_calls: list[dict[str, Any]] = []

    if any(word in lowered for word in ("тариф", "цена", "стоим", "услуг", "что такое delno", "кто вы")):
        result = registry.run(db, ctx, "get_knowledge", query=message)
        tool_calls.append({"tool": "get_knowledge", "ok": isinstance(result, ToolResult) and result.ok})
        if isinstance(result, ToolResult) and result.ok:
            snippets = result.data.get("results") or result.data.get("snippets") or []
            if snippets:
                first = snippets[0]
                text = first.get("text") or first.get("content") or str(first)
                return text[:2000], tool_calls
            return "По базе знаний пока нет точного ответа — передам вопрос менеджеру.", tool_calls
        return "Не удалось получить ответ из базы знаний.", tool_calls

    if any(word in lowered for word in ("заявк", "оставить", "позвон", "связ")):
        return (
            "Могу оформить заявку. Напишите имя и телефон, или используйте форму на сайте.",
            tool_calls,
        )

    if isinstance(result := registry.run(db, ctx, "get_knowledge", query=message), ToolResult) and result.ok:
        tool_calls.append({"tool": "get_knowledge", "ok": True})
        snippets = result.data.get("results") or result.data.get("snippets") or []
        if snippets:
            first = snippets[0]
            text = first.get("text") or first.get("content") or str(first)
            return text[:2000], tool_calls

    return (
        "Я DELNO — ИИ-сотрудник. Могу ответить по услугам и тарифам или помочь оставить заявку. "
        "Спросите текстом или голосом.",
        tool_calls,
    )


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
