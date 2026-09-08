from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.conversation import Message
from app.operator.agent import run_operator_turn
from app.services.channel_router import resolve_public_lead, resolve_widget
from app.services.events import emit_event
from app.services.leads import create_lead_record
from app.services.party_enrichment import suggest_parties_by_query
from app.services.usage import record_usage
from app.services.widget_flow import (
    apply_widget_visitor,
    get_conversation_for_widget,
    lead_summary_for_conversation,
    merge_widget_context,
    tenant_public_profile,
    validate_widget_visitor,
    widget_next_step,
    WidgetVisitorMismatchError,
)
from app.services.widget_security import enforce_widget_rate_limit
from app.services.tts import synthesize_speech
from app.services.instant_demo import preview_website

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
    phone: str | None = Field(default=None, max_length=60)
    page_url: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=500)


class PublicWidgetSession(BaseModel):
    site_key: str = Field(min_length=2, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)
    page_url: str | None = Field(default=None, max_length=500)
    referrer: str | None = Field(default=None, max_length=500)
    channel: str = Field(default="web", max_length=32)


class PublicWidgetVisitorUpdate(BaseModel):
    site_key: str = Field(min_length=2, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=60)


class PublicWidgetMessage(BaseModel):
    site_key: str = Field(min_length=2, max_length=64)
    session_id: str | None = Field(default=None, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)
    message: str = Field(min_length=1, max_length=1200)
    visitor: WidgetVisitor | None = None
    channel: str = Field(default="web", max_length=32)
    input_modality: str = Field(default="text", pattern="^(text|voice)$")


class PublicWidgetHistory(BaseModel):
    site_key: str = Field(min_length=2, max_length=64)
    session_id: str = Field(min_length=8, max_length=64)
    visitor_id: str | None = Field(default=None, max_length=64)


class PublicInstantDemoPreview(BaseModel):
    website_url: str = Field(min_length=4, max_length=500)


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


@router.post("/widget/session")
def public_widget_session(
    body: PublicWidgetSession,
    request: Request,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E3.4 — create or restore widget conversation session."""
    enforce_widget_rate_limit(request, site_key=body.site_key, action="session")
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

    conversation = get_conversation_for_widget(db, ctx, None, create=True)
    assert conversation is not None
    meta = merge_widget_context(
        db,
        conversation,
        visitor_id=body.visitor_id,
        page_url=body.page_url,
        referrer=body.referrer,
    )

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="widget.opened",
        category="operational",
        source="public.widget",
        payload={
            "conversation_id": str(conversation.id),
            "visitor_id": body.visitor_id,
            "page_url": body.page_url,
        },
    )
    db.commit()

    return {
        "session_id": str(conversation.id),
        "tenant_public": tenant_public_profile(db, ctx.tenant_id),
        "widget": {
            "theme": "auto",
            "collect_name": True,
        },
        "lead": lead_summary_for_conversation(db, meta),
        "next_step": widget_next_step(meta),
    }


@router.post("/widget/visitor")
def public_widget_visitor(
    body: PublicWidgetVisitorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E3.8 — persist visitor name/phone and create lead linked to conversation."""
    enforce_widget_rate_limit(request, site_key=body.site_key, action="visitor")
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

    conversation_id = _parse_conversation_id(body.session_id)
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    conversation = get_conversation_for_widget(db, ctx, conversation_id, create=False)
    if not conversation:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        validate_widget_visitor(conversation, body.visitor_id)
    except WidgetVisitorMismatchError:
        raise HTTPException(status_code=403, detail="visitor_mismatch") from None

    if not body.name and not body.phone:
        raise HTTPException(status_code=400, detail="name or phone required")

    merge_widget_context(db, conversation, visitor_id=body.visitor_id)
    result = apply_widget_visitor(
        db,
        ctx,
        conversation,
        name=body.name,
        phone=body.phone,
    )
    db.commit()

    return {
        "ok": True,
        "session_id": str(conversation.id),
        "next_step": result["next_step"],
        "lead": result["lead"],
    }


@router.post("/widget/message")
def public_widget_message(
    body: PublicWidgetMessage,
    request: Request,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E3.4 — public widget chat gateway (guest KB, tenant from site_key)."""
    enforce_widget_rate_limit(request, site_key=body.site_key, action="message")
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

    conversation_id = _parse_conversation_id(body.session_id)
    conversation = get_conversation_for_widget(db, ctx, conversation_id, create=True)
    assert conversation is not None

    try:
        validate_widget_visitor(conversation, body.visitor_id)
    except WidgetVisitorMismatchError:
        raise HTTPException(status_code=403, detail="visitor_mismatch") from None

    merge_widget_context(
        db,
        conversation,
        visitor_id=body.visitor_id,
        page_url=body.visitor.page_url if body.visitor else None,
        referrer=body.visitor.referrer if body.visitor else None,
    )

    visitor_result = apply_widget_visitor(
        db,
        ctx,
        conversation,
        name=body.visitor.name if body.visitor else None,
        phone=body.visitor.phone if body.visitor else None,
    )
    meta = visitor_result["meta"]

    result = run_operator_turn(
        db,
        ctx,
        message=body.message.strip(),
        channel="widget",
        conversation_id=conversation.id,
        input_modality=body.input_modality,
    )

    next_step = widget_next_step(meta)
    if next_step == "ask_name" and len(body.message.strip()) < 8:
        next_step = None

    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="widget.answer_received",
        category="operational",
        source="public.widget",
        payload={"conversation_id": result["conversation_id"]},
    )

    lead = visitor_result["lead"] or lead_summary_for_conversation(db, meta)

    return {
        "message": result["reply"],
        "conversation_id": result["conversation_id"],
        "sources": result.get("sources") or [],
        "next_step": next_step,
        "lead": lead,
    }


@router.post("/widget/history")
def public_widget_history(
    body: PublicWidgetHistory,
    request: Request,
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> dict:
    """E3.4 — load conversation messages for widget session (text + voice unified)."""
    enforce_widget_rate_limit(request, site_key=body.site_key, action="history")
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

    conversation_id = _parse_conversation_id(body.session_id)
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    conversation = get_conversation_for_widget(db, ctx, conversation_id, create=False)
    if not conversation:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        validate_widget_visitor(conversation, body.visitor_id)
    except WidgetVisitorMismatchError:
        raise HTTPException(status_code=403, detail="visitor_mismatch") from None

    rows = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.tenant_id == ctx.tenant_id,
        )
        .order_by(Message.created_at.asc())
        .all()
    )

    messages = []
    for row in rows:
        if row.role not in ("user", "assistant"):
            continue
        meta = row.meta if isinstance(row.meta, dict) else {}
        messages.append(
            {
                "role": row.role,
                "text": row.body,
                "modality": meta.get("modality") or "text",
            }
        )

    return {
        "session_id": str(conversation.id),
        "messages": messages,
    }


@router.get("/widget/tts")
def public_widget_tts(
    request: Request,
    site_key: str = Query(..., min_length=2, max_length=64),
    session_id: str = Query(..., min_length=8, max_length=64),
    text: str = Query(..., min_length=1, max_length=800),
    visitor_id: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
) -> Response:
    """E3.5 — public widget voice output (OpenAI TTS, validated by site_key + session)."""
    enforce_widget_rate_limit(request, site_key=site_key, action="tts")
    channel = _resolve_widget_context(db, site_key)
    if not channel and x_tenant_slug:
        channel = resolve_public_lead(db, x_tenant_slug)
    if not channel:
        raise HTTPException(status_code=404, detail="Unknown site_key")

    ctx = TenantContext(
        tenant_id=channel.tenant_id,
        tenant_slug=channel.tenant_slug,
        role="public",
    )

    conversation_id = _parse_conversation_id(session_id)
    if not conversation_id:
        raise HTTPException(status_code=400, detail="Invalid session_id")

    conversation = get_conversation_for_widget(db, ctx, conversation_id, create=False)
    if not conversation:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        validate_widget_visitor(conversation, visitor_id)
    except WidgetVisitorMismatchError:
        raise HTTPException(status_code=403, detail="visitor_mismatch") from None

    audio, error = synthesize_speech(text)
    if error or not audio:
        code = error or "VOICE_GENERATION_FAILED"
        status = 503 if code == "VOICE_NOT_CONFIGURED" else 502 if code != "TEXT_REQUIRED" else 400
        raise HTTPException(status_code=status, detail=code)

    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "private, max-age=300",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/instant-demo/preview")
def public_instant_demo_preview(
    body: PublicInstantDemoPreview,
    request: Request,
) -> dict:
    """P4 — scrape website preview without persisting (rate limited)."""
    enforce_widget_rate_limit(request, site_key="instant_demo", action="instant_demo")
    try:
        return preview_website(body.website_url)
    except ValueError as exc:
        code = str(exc)
        status = 400
        if code in ("fetch_failed", "url_unreachable"):
            status = 502
        raise HTTPException(status_code=status, detail=code) from exc
