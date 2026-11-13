from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.services import crm as crm_service
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


class LeadLifecyclePatch(BaseModel):
    status: str = Field(min_length=2, max_length=32)


@router.get("")
def list_leads(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """List tenant leads (cabinet / CRM-lite)."""
    rows = (
        db.query(Lead)
        .filter(Lead.tenant_id == ctx.tenant_id)
        .order_by(Lead.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "items": [
            {
                "id": str(row.id),
                "name": row.name,
                "phone": row.phone,
                "email": row.email,
                "company": row.company,
                "website": row.website,
                "inn": row.inn,
                "source": row.source,
                "status": row.status,
                "conversation_id": str(row.conversation_id) if row.conversation_id else None,
                "party_enriched": row.party_json is not None,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }


@router.post("")
def create_lead(
    body: LeadCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
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


@router.get("/funnel")
def leads_funnel(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """CRM-lite funnel counts for the cabinet."""
    return crm_service.funnel_counts(db, ctx)


@router.patch("/{lead_id}/lifecycle")
def patch_lead_lifecycle(
    lead_id: str,
    body: LeadLifecyclePatch,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    result = crm_service.set_lifecycle(db, ctx, lead_id=lead_id, status=body.status)
    if not result.get("ok"):
        err = result.get("error")
        if err == "not_found":
            raise HTTPException(status_code=404, detail="lead not found")
        if err == "invalid_status":
            raise HTTPException(status_code=400, detail=result)
        raise HTTPException(status_code=400, detail=result)
    db.commit()
    return result
