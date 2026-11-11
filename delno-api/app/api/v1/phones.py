"""Tenant phone (DID) provisioning — Hermes / owner."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services import phone_provision

router = APIRouter(prefix="/tenant/phones", tags=["tenant-phones"])


class ProvisionPhoneRequest(BaseModel):
    e164: str = Field(min_length=8, max_length=20)
    label: str | None = Field(default="main", max_length=120)
    status: str = Field(default="active", max_length=32)


class PhoneStatusRequest(BaseModel):
    status: str = Field(min_length=2, max_length=32)


def _require_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("")
def phones_list(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return phone_provision.list_phones(db, ctx)


@router.post("")
def phones_provision(
    body: ProvisionPhoneRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    out = phone_provision.provision_phone(
        db, ctx, e164=body.e164, label=body.label, status=body.status
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error"))
    return out


@router.post("/{phone_id}/status")
def phones_status(
    phone_id: UUID,
    body: PhoneStatusRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    out = phone_provision.set_phone_status(db, ctx, phone_id, status=body.status)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error"))
    return out
