from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenant import TenantContext, get_tenant_context
from app.services.leads import create_lead_record
from app.services.usage import record_usage

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    inn: str | None = Field(default=None, max_length=14)
    source: str = Field(default="website", max_length=120)


@router.post("")
def create_lead(
    body: LeadCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
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
        audit_action="lead.create",
        event_source="api.leads",
        channel=body.source,
    )
    record_usage(db, tenant_id=ctx.tenant_id, metric="leads.created", quantity=1)
    db.commit()
    return {
        "ok": True,
        "lead_id": str(lead.id),
        "telegram_notified": meta["telegram_notified"],
        "party_enriched": meta["enrichment"].get("enriched"),
        "inn": lead.inn,
    }
