"""E2.3 — tenant channel connect endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services.telegram_connect import (
    connect_telegram_branded,
    disconnect_telegram_branded,
    healthcheck_telegram_branded,
    list_tenant_channels,
)

router = APIRouter(prefix="/tenant/channels", tags=["tenant-channels"])


class TelegramConnectRequest(BaseModel):
    bot_token: str = Field(min_length=20, max_length=120)


def _require_tenant_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("")
def tenant_channels_list(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    return list_tenant_channels(db, ctx)


@router.post("/telegram/connect")
def tenant_telegram_connect(
    body: TelegramConnectRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = connect_telegram_branded(db, ctx, body.bot_token)
    if not result.get("ok"):
        code = 400 if result.get("error") in ("invalid_token_format", "token_already_linked") else 502
        raise HTTPException(status_code=code, detail=result.get("error"))
    return result


@router.post("/telegram/{account_id}/disconnect")
def tenant_telegram_disconnect(
    account_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = disconnect_telegram_branded(db, ctx, account_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/telegram/{account_id}/health")
def tenant_telegram_health(
    account_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = healthcheck_telegram_branded(db, ctx, account_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="not_found")
    return result
