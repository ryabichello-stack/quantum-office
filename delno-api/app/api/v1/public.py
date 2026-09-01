from datetime import datetime, timezone

from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.services.audit import write_audit
from app.services.channel_router import resolve_public_lead
from app.services.events import emit_event
from app.services.leads import notify_lead_telegram
from app.services.usage import record_usage

router = APIRouter(prefix="/public", tags=["public"])


class PublicLeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    source: str = Field(default="website", max_length=120)


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

    lead = Lead(
        tenant_id=channel.tenant_id,
        source=body.source,
        name=body.name.strip(),
        phone=body.phone.strip(),
        email=body.email.strip() if body.email else None,
        company=body.company.strip() if body.company else None,
        website=body.website.strip() if body.website else None,
    )
    db.add(lead)
    db.flush()
    notified = notify_lead_telegram(lead)

    ctx = TenantContext(tenant_id=channel.tenant_id, tenant_slug=channel.tenant_slug, role="public")
    write_audit(
        db,
        ctx,
        action="lead.create.public",
        resource=f"lead:{lead.id}",
        new_value={"name": lead.name, "phone": lead.phone, "source": lead.source},
    )
    emit_event(
        db,
        tenant_id=channel.tenant_id,
        event_type="lead.created",
        category="domain",
        payload={"lead_id": str(lead.id), "source": lead.source, "channel": "website"},
    )
    record_usage(db, tenant_id=channel.tenant_id, metric="leads.created", quantity=1)
    db.commit()
    return {"ok": True, "lead_id": str(lead.id), "telegram_notified": notified}


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
