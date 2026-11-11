"""E2.3/E2.4 — tenant channel connect endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services import channel_qr
from app.services.max_connect import (
    connect_max_branded,
    disconnect_max_branded,
    healthcheck_max_branded,
    list_tenant_channels,
)
from app.services.telegram_connect import (
    connect_telegram_branded,
    disconnect_telegram_branded,
    healthcheck_telegram_branded,
)

router = APIRouter(prefix="/tenant/channels", tags=["tenant-channels"])


class TelegramConnectRequest(BaseModel):
    bot_token: str = Field(min_length=20, max_length=120)


class MaxConnectRequest(BaseModel):
    access_token: str = Field(min_length=16, max_length=256)


class QrStartRequest(BaseModel):
    channel_type: str = Field(min_length=3, max_length=32)
    label: str | None = Field(default=None, max_length=120)


class QrConfirmRequest(BaseModel):
    session_material: str = Field(min_length=20, max_length=20000)


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


@router.post("/max/connect")
def tenant_max_connect(
    body: MaxConnectRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = connect_max_branded(db, ctx, body.access_token)
    if not result.get("ok"):
        code = 400 if result.get("error") in ("invalid_token_format", "token_already_linked", "not_a_bot") else 502
        raise HTTPException(status_code=code, detail=result.get("error"))
    return result


@router.post("/max/{account_id}/disconnect")
def tenant_max_disconnect(
    account_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = disconnect_max_branded(db, ctx, account_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result


@router.get("/max/{account_id}/health")
def tenant_max_health(
    account_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = healthcheck_max_branded(db, ctx, account_id)
    if result.get("error") == "not_found":
        raise HTTPException(status_code=404, detail="not_found")
    return result


@router.post("/qr/start")
def tenant_channel_qr_start(
    body: QrStartRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """Start QR / web-session login (alternative to bot token)."""
    _require_tenant_admin(ctx)
    result = channel_qr.start_qr_login(db, ctx, channel_type=body.channel_type, label=body.label)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.post("/qr/{account_id}/confirm")
def tenant_channel_qr_confirm(
    account_id: UUID,
    body: QrConfirmRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = channel_qr.confirm_qr_session(db, ctx, account_id=account_id, session_material=body.session_material)
    if not result.get("ok"):
        code = 404 if result.get("error") == "not_found" else 400
        raise HTTPException(status_code=code, detail=result.get("error"))
    return result


@router.get("/qr/{account_id}")
def tenant_channel_qr_status(
    account_id: UUID,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_tenant_admin(ctx)
    result = channel_qr.qr_status(db, ctx, account_id=account_id)
    if not result.get("ok"):
        raise HTTPException(status_code=404, detail=result.get("error"))
    return result
