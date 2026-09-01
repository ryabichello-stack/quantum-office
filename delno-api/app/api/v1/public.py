from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.operator.agent import run_operator_turn
from app.services.channel_router import resolve_public_lead, resolve_widget
from app.services.events import emit_event
from app.services.leads import create_lead_record
from app.services.party_enrichment import suggest_parties_by_query
from app.services.usage import record_usage

router = APIRouter(prefix="/public", tags=["public"])


class PublicLeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=14)
    source: str = Field(default="website", max_length=120)


class PublicPartySuggest(BaseModel):
    q: str = Field(min_length=2, max_length=120)
    count: int = Field(default=5, ge=1, le=10)


@router.post("/party/suggest")
def public_party_suggest(
    body: PublicPartySuggest,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E1.14 — server-side DaData party suggest for marketing site (no API key in browser)."""
    from app.core.config import get_settings

    slug = x_tenant_slug or get_settings().default_tenant_slug
    channel = resolve_public_lead(db, slug)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {slug}")

    result = suggest_parties_by_query(
        db,
        body.q,
        tenant_id=channel.tenant_id,
        count=body.count,
        source="public.party.suggest",
    )
    if not result.get("ok") and result.get("error") == "query_too_short":
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    db.commit()
    return result


@router.post("/leads")
def create_public_lead(
    body: PublicLeadCreate,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    from app.core.config import get_settings

    slug = x_tenant_slug or get_settings().default_tenant_slug
    channel = resolve_public_lead(db, slug)
    if not channel:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {slug}")

    ctx = TenantContext(tenant_id=channel.tenant_id, tenant_slug=channel.tenant_slug, role="public")
    lead, meta = create_lead_record(
        db,
        ctx,
        name=body.name,
        phone=body.phone,
        email=body.email,
        company=body.company,
        website=body.website,
        source=body.source,
        inn=body.inn,
        audit_action="lead.create.public",
        event_source="public.leads",
        channel="website",
    )
    record_usage(db, tenant_id=channel.tenant_id, metric="leads.created", quantity=1)
    db.commit()
    return {
        "ok": True,
        "lead_id": str(lead.id),
        "telegram_notified": meta["telegram_notified"],
        "party_enriched": meta["enrichment"].get("enriched"),
        "inn": lead.inn,
    }


@router.get("/cms/pages/{slug}")
def get_published_cms_page(
    slug: str,
    db: Session = Depends(get_db),
    locale: str = "ru",
) -> dict:
    from app.models.cms import CmsPage

    page = (
        db.query(CmsPage)
        .filter(
            CmsPage.slug == slug,
            CmsPage.locale == locale,
            CmsPage.status == "published",
            CmsPage.tenant_id.is_(None),
        )
        .one_or_none()
    )
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return {
        "slug": page.slug,
        "title": page.title,
        "blocks": page.blocks,
        "published_at": page.published_at.isoformat() if page.published_at else None,
    }


class WidgetVisitor(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    page_url: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=500)


class PublicWidgetMessage(BaseModel):
    site_key: str = Field(min_length=2, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=1200)
    visitor: WidgetVisitor | None = None
    channel: str = Field(default="web", max_length=32)


def _resolve_widget_context(db: Session, site_key: str):
    ctx = resolve_widget(db, site_key)
    if ctx:
        return ctx
    if site_key in ("demo_dlno", "demo"):
        return resolve_public_lead(db, get_settings().default_tenant_slug)
    return None


def _parse_conversation_id(session_id: str | None) -> UUID | None:
    if not session_id:
        return None
    try:
        return UUID(session_id)
    except ValueError:
        return None


@router.post("/widget/message")
def public_widget_message(
    body: PublicWidgetMessage,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E3.4 — public widget chat gateway (guest KB, tenant from site_key)."""
    channel = _resolve_widget_context(db, body.site_key)
    if not channel and x_tenant_slug:
        channel = resolve_public_lead(db, x_tenant_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Unknown site_key")

    ctx = TenantContext(
        tenant_id=channel.tenant_id,
        tenant_slug=channel.tenant_slug,
        role="public",
    )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="widget.message_sent",
        category="operational",
        source="public.widget",
        payload={
            "visitor_id": body.visitor_id,
            "channel": body.channel,
            "page_url": body.visitor.page_url if body.visitor else None,
        },
    )

    result = run_operator_turn(
        db,
        ctx,
        message=body.message.strip(),
        channel="widget",
        conversation_id=_parse_conversation_id(body.session_id),
        input_modality="text",
    )

    visitor_name = body.visitor.name if body.visitor else None
    next_step = None
    if not visitor_name and len(body.message.strip()) >= 8:
        next_step = "ask_name"

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="widget.answer_received",
        category="operational",
        source="public.widget",
        payload={"conversation_id": result["conversation_id"]},
    )

    return {
        "message": result["reply"],
        "conversation_id": result["conversation_id"],
        "sources": result.get("sources") or [],
        "next_step": next_step,
    }
