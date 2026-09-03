"""Widget session visitor profile + lead capture (E3.8)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.conversation import Conversation
from app.models.lead import Lead
from app.models.tenant import Tenant
from app.services.events import emit_event
from app.services.leads import create_lead_record

_PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str | None:
    digits = _PHONE_DIGITS.sub("", raw.strip())
    if len(digits) == 11 and digits.startswith("8"):
        digits = "7" + digits[1:]
    if len(digits) == 10:
        digits = "7" + digits
    if len(digits) == 11 and digits.startswith("7"):
        return f"+{digits}"
    return None


def conversation_meta(conversation: Conversation) -> dict[str, Any]:
    meta = conversation.meta
    return dict(meta) if isinstance(meta, dict) else {}


def widget_next_step(meta: dict[str, Any], *, visitor_name: str | None = None) -> str | None:
    name = (visitor_name or meta.get("visitor_name") or "").strip()
    if not name:
        return "ask_name"
    if not meta.get("lead_id"):
        return "ask_phone"
    return None


def get_conversation_for_widget(
    db: Session,
    ctx: TenantContext,
    session_id: uuid.UUID | None,
    *,
    create: bool = False,
) -> Conversation | None:
    if session_id:
        row = (
            db.query(Conversation)
            .filter(Conversation.id == session_id, Conversation.tenant_id == ctx.tenant_id)
            .one_or_none()
        )
        if row:
            return row
    if not create:
        return None
    row = Conversation(tenant_id=ctx.tenant_id, channel="widget", meta={})
    db.add(row)
    db.flush()
    return row


def merge_widget_context(
    db: Session,
    conversation: Conversation,
    *,
    visitor_id: str | None = None,
    page_url: str | None = None,
    referrer: str | None = None,
) -> dict[str, Any]:
    meta = conversation_meta(conversation)
    if visitor_id and not meta.get("visitor_id"):
        meta["visitor_id"] = visitor_id
    if page_url and not meta.get("page_url"):
        meta["page_url"] = page_url
    if referrer and not meta.get("referrer"):
        meta["referrer"] = referrer
    conversation.meta = meta
    if meta.get("visitor_name"):
        conversation.contact_ref = str(meta["visitor_name"])[:200]
    db.flush()
    return meta


def apply_widget_visitor(
    db: Session,
    ctx: TenantContext,
    conversation: Conversation,
    *,
    name: str | None = None,
    phone: str | None = None,
) -> dict[str, Any]:
    """Persist visitor name/phone on conversation and create lead when ready."""
    meta = conversation_meta(conversation)
    lead_info: dict[str, Any] | None = None

    clean_name = (name or "").strip()
    if clean_name and not meta.get("visitor_name"):
        meta["visitor_name"] = clean_name
        conversation.contact_ref = clean_name[:200]
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="widget.name_collected",
            category="operational",
            source="public.widget",
            payload={
                "conversation_id": str(conversation.id),
                "visitor_name": clean_name,
            },
        )

    normalized_phone = normalize_phone(phone) if phone else None
    if normalized_phone and not meta.get("lead_id"):
        lead_name = (meta.get("visitor_name") or clean_name or "Посетитель").strip()
        lead, _meta = create_lead_record(
            db,
            ctx,
            name=lead_name,
            phone=normalized_phone,
            source="widget",
            audit_action="lead.create.widget",
            event_source="public.widget",
            channel="widget",
            conversation_id=conversation.id,
        )
        meta["lead_id"] = str(lead.id)
        meta["visitor_phone"] = normalized_phone
        emit_event(
            db,
            tenant_id=ctx.tenant_id,
            event_type="widget.lead_created",
            category="operational",
            source="public.widget",
            payload={
                "conversation_id": str(conversation.id),
                "lead_id": str(lead.id),
                "visitor_name": lead_name,
            },
        )
        lead_info = {"id": str(lead.id), "name": lead.name, "phone": lead.phone}

    conversation.meta = meta
    db.flush()

    return {
        "meta": meta,
        "lead": lead_info,
        "next_step": widget_next_step(meta, visitor_name=clean_name or None),
    }


def tenant_public_profile(db: Session, tenant_id: uuid.UUID) -> dict[str, str]:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
    if not tenant:
        return {"name": "DELNO", "assistant_name": "DELNO"}
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    assistant = str(settings.get("assistant_name") or "DELNO")
    return {"name": tenant.name, "assistant_name": assistant}


def lead_summary_for_conversation(db: Session, meta: dict[str, Any]) -> dict[str, Any] | None:
    lead_id = meta.get("lead_id")
    if not lead_id:
        return None
    try:
        lead_uuid = uuid.UUID(str(lead_id))
    except ValueError:
        return None
    lead = db.query(Lead).filter(Lead.id == lead_uuid).one_or_none()
    if not lead:
        return None
    return {"id": str(lead.id), "name": lead.name, "phone": lead.phone}
