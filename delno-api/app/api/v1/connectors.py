from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.adapters.connectors import CONNECTOR_KINDS
from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services.connector_connect import (
    catalog,
    connect_provider,
    google_oauth_finish,
    google_oauth_start,
    link_status,
    reprobe,
)
from app.services.connectors import list_tenant_connectors, probe_tenant_connector, update_tenant_connector

router = APIRouter(prefix="/tenant/connectors", tags=["tenant-connectors"])


class ConnectorUpdate(BaseModel):
    enabled: bool | None = None
    base_url: str | None = Field(default=None, max_length=500)
    webhook_token: str | None = Field(default=None, max_length=500)


def _require_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Insufficient role")


@router.get("")
def get_connectors(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """List office connectors for this tenant (mail/calendar/files/conference/outreach)."""
    return list_tenant_connectors(db, ctx)


@router.patch("/{kind}")
def patch_connector(
    kind: str,
    body: ConnectorUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    if kind not in CONNECTOR_KINDS:
        raise HTTPException(status_code=404, detail="Unknown connector kind")
    result = update_tenant_connector(
        db,
        ctx,
        kind,
        enabled=body.enabled,
        base_url=body.base_url,
        webhook_token=body.webhook_token,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "update_failed")
    return result


@router.post("/{kind}/probe")
def probe_connector(
    kind: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    if kind not in CONNECTOR_KINDS:
        raise HTTPException(status_code=404, detail="Unknown connector kind")
    return probe_tenant_connector(db, ctx, kind)


class ConnectBody(BaseModel):
    provider: str = Field(..., max_length=40)
    login: str | None = Field(default=None, max_length=120)
    password: str | None = Field(default=None, max_length=4096)
    calendar_url: str | None = Field(default=None, max_length=500)
    foreign_consent: bool = False


class GoogleFinishBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=2048)
    state: str = Field(..., min_length=8, max_length=200)


@router.get("/connect/{kind}")
def connect_catalog(
    kind: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    providers = catalog(kind)
    if not providers:
        raise HTTPException(status_code=404, detail="Unknown connector kind")
    return {"ok": True, "kind": kind, "providers": providers, "connection": link_status(db, ctx, kind)}


@router.post("/connect/{kind}")
def connect_submit(
    kind: str,
    body: ConnectBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    result = connect_provider(
        db,
        ctx,
        kind=kind,
        provider=body.provider,
        login=body.login,
        password=body.password,
        calendar_url=body.calendar_url,
        foreign_consent=body.foreign_consent,
    )
    if result.get("error") in {"unsupported_kind", "unknown_provider"}:
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/connect/{kind}/reprobe")
def connect_reprobe(
    kind: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return reprobe(db, ctx, kind=kind)


@router.post("/connect/calendar/oauth/google/start")
def google_calendar_oauth_start(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return google_oauth_start(db, ctx)


@router.post("/connect/calendar/oauth/google/finish")
def google_calendar_oauth_finish(
    body: GoogleFinishBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    _require_admin(ctx)
    return google_oauth_finish(db, ctx, code=body.code, state=body.state)
