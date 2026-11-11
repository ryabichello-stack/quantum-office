"""Tenant billing — token balance, tariff, usage summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import billing as billing_svc

router = APIRouter(prefix="/tenant/billing", tags=["tenant-billing"])


class TopUpRequest(BaseModel):
    amount: float = Field(gt=0, le=1_000_000)
    note: str | None = Field(default=None, max_length=200)


def _require_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/summary")
def billing_summary(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return billing_svc.usage_summary(db, ctx)


@router.post("/ensure")
def billing_ensure(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    billing_svc.ensure_billing_defaults(db, tenant, grant_credits=500.0)
    db.commit()
    return billing_svc.usage_summary(db, ctx)


@router.post("/topup")
def billing_topup(
    body: TopUpRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    if ctx.role != "platform_admin" and body.amount > 50_000:
        raise HTTPException(status_code=400, detail="amount_too_large")
    return billing_svc.top_up(db, ctx, amount=body.amount, note=body.note)
