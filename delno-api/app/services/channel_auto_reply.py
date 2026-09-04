"""E2.2 — auto-reply for inbound channel messages via Conversation Core."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.adapters.channels.base import ChannelAdapter, InboundMessage, OutboundMessage
from app.core.tenant import TenantContext
from app.models.conversation import Message
from app.operator.agent import run_operator_turn
from app.services.channel_router import ChannelContext
from app.services.events import emit_event
from app.services.inbound_messages import record_inbound_message
from app.services.widget_flow import conversation_meta

_FALLBACK_REPLY = (
    "Сейчас не могу ответить. Попробуйте позже или оставьте заявку на сайте — с вами свяжутся."
)


def _tenant_ctx(ctx: ChannelContext) -> TenantContext:
    return TenantContext(
        tenant_id=ctx.tenant_id,
        tenant_slug=ctx.tenant_slug,
        role="public",
    )


def _operator_reply(
    db: Session,
    ctx: ChannelContext,
    inbound: InboundMessage,
    conversation_id,
) -> dict[str, Any]:
    try:
        return run_operator_turn(
            db,
            _tenant_ctx(ctx),
            message=inbound.text,
            channel=inbound.channel_type,
            conversation_id=conversation_id,
            input_modality="text",
            record_user_message=False,
            commit=False,
        )
    except Exception:
        assistant = Message(
            tenant_id=ctx.tenant_id,
            conversation_id=conversation_id,
            role="assistant",
            body=_FALLBACK_REPLY,
            meta={"source": f"webhook.{inbound.channel_type}.fallback"},
        )
        db.add(assistant)
        db.flush()
        return {"reply": _FALLBACK_REPLY, "conversation_id": str(conversation_id)}


def process_inbound_auto_reply(
    db: Session,
    ctx: ChannelContext,
    inbound: InboundMessage,
    *,
    adapter: ChannelAdapter,
    credentials: dict[str, Any],
) -> dict[str, Any]:
    """Record inbound message, generate operator reply, deliver via channel adapter."""
    conversation, user_message = record_inbound_message(db, ctx, inbound)
    result = _operator_reply(db, ctx, inbound, conversation.id)
    reply_text = str(result.get("reply") or _FALLBACK_REPLY).strip() or _FALLBACK_REPLY

    meta = conversation_meta(conversation)
    meta["last_reply_preview"] = reply_text[:240]
    conversation.meta = meta

    send_result = adapter.send_reply(
        external_user_id=inbound.external_user_id,
        message=OutboundMessage(text=reply_text),
        credentials=credentials,
    )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="message.sent",
        category="operational",
        source=f"webhook.{inbound.channel_type}",
        payload={
            "conversation_id": str(conversation.id),
            "user_message_id": str(user_message.id),
            "channel": inbound.channel_type,
            "external_user_id": inbound.external_user_id,
            "delivered": bool(send_result.get("ok")),
            "telegram_message_id": send_result.get("message_id"),
        },
    )

    return {
        "conversation_id": str(conversation.id),
        "message_id": str(user_message.id),
        "reply": reply_text,
        "delivered": bool(send_result.get("ok")),
        "send_error": None if send_result.get("ok") else send_result.get("error") or send_result.get("detail"),
    }
