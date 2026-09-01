from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.tenant import TenantContext, get_tenant_context
from app.models.lead import Lead
from app.operator.agent import run_operator_turn
from app.services.audit import write_audit
from app.services.leads import notify_lead_telegram

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=3, max_length=60)
    email: str | None = Field(default=None, max_length=160)
    company: str | None = Field(default=None, max_length=160)
    website: str | None = Field(default=None, max_length=255)
    source: str = Field(default="website", max_length=120)


@router.post("")
def create_lead(
    body: LeadCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
) -> dict:
    lead = Lead(
        tenant_id=ctx.tenant_id,
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
    write_audit(
        db,
        ctx,
        action="lead.create",
        resource=f"lead:{lead.id}",
        new_value={"name": lead.name, "phone": lead.phone, "source": lead.source},
    )
    db.commit()
    return {"ok": True, "lead_id": str(lead.id), "telegram_notified": notified}
