"""E2.7 — persist inbound channel messages as conversations."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.adapters.channels.base import InboundMessage
from app.models.conversation import Conversation, Message
from app.services.channel_router import ChannelContext
from app.services.events import emit_event
from app.services.widget_flow import conversation_meta


def _contact_ref(channel_type: str, external_user_id: str) -> str:
    prefix = "tg" if channel_type == "telegram" else channel_type[:8]
    return f"{prefix}:{external_user_id}"[:200]


def find_or_create_conversation(
    db: Session,
    ctx: ChannelContext,
    inbound: InboundMessage,
) -> Conversation:
    ref = _contact_ref(inbound.channel_type, inbound.external_user_id)
    row = (
        db.query(Conversation)
        .filter(
            Conversation.tenant_id == ctx.tenant_id,
            Conversation.channel == inbound.channel_type,
            Conversation.contact_ref == ref,
        )
        .order_by(Conversation.updated_at.desc())
        .first()
    )
    if row:
        return row

    meta: dict[str, Any] = {
        "external_user_id": inbound.external_user_id,
        "channel_account_id": str(ctx.channel_account_id) if ctx.channel_account_id else None,
    }
    if inbound.display_name:
        meta["visitor_name"] = inbound.display_name
    if inbound.username:
        meta["telegram_username"] = inbound.username

    row = Conversation(
        tenant_id=ctx.tenant_id,
        channel=inbound.channel_type,
        contact_ref=ref,
        meta=meta,
    )
    db.add(row)
    db.flush()
    return row


def record_inbound_message(
    db: Session,
    ctx: ChannelContext,
    inbound: InboundMessage,
) -> tuple[Conversation, Message]:
    conversation = find_or_create_conversation(db, ctx, inbound)

    meta = conversation_meta(conversation)
    if inbound.display_name and not meta.get("visitor_name"):
        meta["visitor_name"] = inbound.display_name
    if inbound.username and not meta.get("telegram_username"):
        meta["telegram_username"] = inbound.username
    meta["last_message_preview"] = inbound.text[:240]
    conversation.meta = meta
    conversation.status = "open"

    message = Message(
        tenant_id=ctx.tenant_id,
        conversation_id=conversation.id,
        role="user",
        body=inbound.text,
        meta={"source": f"webhook.{inbound.channel_type}"},
    )
    db.add(message)
    db.flush()

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="message.received",
        category="operational",
        source=f"webhook.{inbound.channel_type}",
        payload={
            "conversation_id": str(conversation.id),
            "message_id": str(message.id),
            "channel": inbound.channel_type,
            "external_user_id": inbound.external_user_id,
        },
    )
    return conversation, message


def resolve_channel_account(db: Session, account_id: UUID):
    from app.models.channel_account import ChannelAccount

    return (
        db.query(ChannelAccount)
        .filter(ChannelAccount.id == account_id, ChannelAccount.status == "active")
        .one_or_none()
    )
