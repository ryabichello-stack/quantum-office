"""Secure credential forms — never log plaintext passwords."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services import tenant_vault

router = APIRouter(prefix="/tenant/vault", tags=["tenant-vault"])


class SaveCredentialRequest(BaseModel):
    kind: str = Field(default="mango_sip", max_length=64)
    login: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=4096)
    foreign_consent: bool = False


def _require_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("")
def credentials_status(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return tenant_vault.list_secret_status(db, ctx)


@router.get("/forms/{kind}")
def credential_form(
    kind: str,
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return {"ok": True, "form": tenant_vault.credential_form_spec(kind)}


@router.post("")
def credentials_save(
    body: SaveCredentialRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    out = tenant_vault.save_secret(
        db,
        ctx,
        kind=body.kind,
        login=body.login,
        password=body.password,
        foreign_consent=bool(body.foreign_consent),
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error") or "failed")
    return out
