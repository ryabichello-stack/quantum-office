"""Serialize conversations for cabinet inbox (names, preview, channel labels)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.conversation import Conversation, Message
from app.models.lead import Lead


def mask_phone(phone: str | None) -> str | None:
    if not phone:
        return None
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) < 10:
        return phone
    tail = digits[-2:]
    if len(digits) == 11 and digits.startswith("7"):
        return f"+7 {digits[1:4]} ••• •• {tail}"
    if len(digits) == 11 and digits.startswith("8"):
        return f"+7 {digits[1:4]} ••• •• {tail}"
    return f"+{digits[0]} ••• •• {tail}"


def channel_label(channel: str, meta: dict[str, Any] | None = None) -> str:
    c = (channel or "web").lower()
    meta = meta or {}
    if meta.get("call_direction") == "inbound" or "phone" in c or "call" in c:
        return "Входящий звонок"
    if "widget" in c or c == "web":
        return "Чат на сайте"
    if "cabinet" in c or c == "operator":
        return "Operator · кабинет"
    if "telegram" in c:
        return "Telegram"
    if "mail" in c or "email" in c:
        return "Email"
    if "max" in c:
        return "MAX"
    return channel or "Диалог"


def _meta_dict(row: Conversation) -> dict[str, Any]:
    return row.meta if isinstance(row.meta, dict) else {}


def _resolve_contact(
    meta: dict[str, Any],
    lead: Lead | None,
) -> tuple[str | None, str | None]:
    name = (meta.get("visitor_name") or meta.get("name") or "").strip() or None
    phone = (meta.get("visitor_phone") or meta.get("phone") or "").strip() or None
    if lead:
        name = name or (lead.name or "").strip() or None
        phone = phone or (lead.phone or "").strip() or None
    return name, phone


def _last_messages_map(db: Session, tenant_id: uuid.UUID, conversation_ids: list[uuid.UUID]) -> dict[uuid.UUID, Message]:
    if not conversation_ids:
        return {}
    subq = (
        db.query(
            Message.conversation_id.label("cid"),
            func.max(Message.created_at).label("max_at"),
        )
        .filter(Message.tenant_id == tenant_id, Message.conversation_id.in_(conversation_ids))
        .group_by(Message.conversation_id)
        .subquery()
    )
    rows = (
        db.query(Message)
        .join(
            subq,
            (Message.conversation_id == subq.c.cid) & (Message.created_at == subq.c.max_at),
        )
        .all()
    )
    return {row.conversation_id: row for row in rows}


def _leads_map(
    db: Session,
    tenant_id: uuid.UUID,
    conversations: list[Conversation],
) -> tuple[dict[str, Lead], dict[uuid.UUID, Lead]]:
    by_id: dict[str, Lead] = {}
    by_conv: dict[uuid.UUID, Lead] = {}
    lead_ids: list[uuid.UUID] = []
    conv_ids = [c.id for c in conversations]

    for conv in conversations:
        meta = _meta_dict(conv)
        raw = meta.get("lead_id")
        if raw:
            try:
                lead_ids.append(uuid.UUID(str(raw)))
            except ValueError:
                pass

    if lead_ids:
        for lead in db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.id.in_(lead_ids)).all():
            by_id[str(lead.id)] = lead

    if conv_ids:
        for lead in db.query(Lead).filter(Lead.tenant_id == tenant_id, Lead.conversation_id.in_(conv_ids)).all():
            if lead.conversation_id:
                by_conv[lead.conversation_id] = lead

    return by_id, by_conv


def _lead_for_conversation(
    conv: Conversation,
    meta: dict[str, Any],
    by_id: dict[str, Lead],
    by_conv: dict[uuid.UUID, Lead],
) -> Lead | None:
    if conv.id in by_conv:
        return by_conv[conv.id]
    raw = meta.get("lead_id")
    if raw and str(raw) in by_id:
        return by_id[str(raw)]
    return None


def serialize_conversation_item(
    conv: Conversation,
    *,
    lead: Lead | None,
    last_message: Message | None,
) -> dict[str, Any]:
    meta = _meta_dict(conv)
    name, phone = _resolve_contact(meta, lead)
    preview = ""
    if last_message and last_message.body:
        preview = last_message.body.strip()[:120]
    elif meta.get("last_message_preview"):
        preview = str(meta["last_message_preview"])[:120]

    updated = conv.updated_at or conv.created_at
    is_new = conv.status == "open" or conv.status == "new"

    return {
        "id": str(conv.id),
        "channel": conv.channel,
        "channel_label": channel_label(conv.channel, meta),
        "status": conv.status,
        "contact_ref": conv.contact_ref,
        "visitor_name": name,
        "visitor_phone": phone,
        "visitor_phone_masked": mask_phone(phone),
        "lead_id": str(lead.id) if lead else meta.get("lead_id"),
        "last_message_preview": preview,
        "message_count": meta.get("message_count"),
        "is_new": is_new,
        "created_at": conv.created_at.isoformat() if conv.created_at else None,
        "updated_at": updated.isoformat() if updated else None,
    }


def serialize_conversation_detail(
    conv: Conversation,
    *,
    lead: Lead | None,
    message_count: int,
) -> dict[str, Any]:
    meta = _meta_dict(conv)
    name, phone = _resolve_contact(meta, lead)
    base = serialize_conversation_item(conv, lead=lead, last_message=None)
    base.update(
        {
            "summary": meta.get("summary"),
            "tags": meta.get("tags") if isinstance(meta.get("tags"), list) else [],
            "recording_url": meta.get("recording_url"),
            "recording_duration_sec": meta.get("recording_duration_sec"),
            "call_status": meta.get("call_status") or ("completed" if meta.get("recording_url") else None),
            "message_count": message_count,
            "subtitle": f"{base['channel_label']} · {base['visitor_phone_masked'] or 'контакт не указан'}",
        }
    )
    if name:
        base["visitor_name"] = name
    if phone:
        base["visitor_phone"] = phone
    return base


def list_conversation_items(db: Session, tenant_id: uuid.UUID, rows: list[Conversation]) -> list[dict[str, Any]]:
    if not rows:
        return []
    conv_ids = [r.id for r in rows]
    by_id, by_conv = _leads_map(db, tenant_id, rows)
    last_map = _last_messages_map(db, tenant_id, conv_ids)
    items = []
    for conv in rows:
        meta = _meta_dict(conv)
        lead = _lead_for_conversation(conv, meta, by_id, by_conv)
        items.append(
            serialize_conversation_item(
                conv,
                lead=lead,
                last_message=last_map.get(conv.id),
            )
        )
    return items


def filter_conversation_items(
    items: list[dict[str, Any]],
    *,
    q: str | None = None,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    out = items
    if status_filter == "new":
        out = [i for i in out if i.get("is_new")]
    elif status_filter == "mine":
        out = [i for i in out if "cabinet" in (i.get("channel") or "").lower() or i.get("channel") == "operator"]

    query = (q or "").strip().lower()
    if not query:
        return out
    filtered: list[dict[str, Any]] = []
    for item in out:
        hay = " ".join(
            str(item.get(k) or "")
            for k in ("visitor_name", "visitor_phone", "last_message_preview", "channel_label", "contact_ref")
        ).lower()
        if query in hay:
            filtered.append(item)
    return filtered


def get_conversation_detail(db: Session, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> dict[str, Any] | None:
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conversation_id, Conversation.tenant_id == tenant_id)
        .one_or_none()
    )
    if not conv:
        return None
    by_id, by_conv = _leads_map(db, tenant_id, [conv])
    meta = _meta_dict(conv)
    lead = _lead_for_conversation(conv, meta, by_id, by_conv)
    message_count = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id, Message.tenant_id == tenant_id)
        .count()
    )
    return serialize_conversation_detail(conv, lead=lead, message_count=message_count)
