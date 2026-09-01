from datetime import datetime, timezone

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services.channel_router import resolve_public_lead
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
