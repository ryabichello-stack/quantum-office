"""Owner-facing bridge to Nous Hermes runtimes (feature-flagged)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services.hermes_nous.bridge import HermesBridgeError, create_run, get_run, stop_run
from app.services.hermes_nous.flags import FLAG_HERMES_NOUS_RUNTIME, is_hermes_nous_enabled
from app.services.hermes_nous.provision import ensure_tenant_hermes_home, tenant_runtime_record
from app.services.hermes_nous.run_tokens import issue_run_token, revoke_run_token

router = APIRouter(prefix="/hermes-nous", tags=["hermes-nous"])


def _require_flag(db: Session, ctx: TenantContext) -> None:
    if not is_hermes_nous_enabled(db, ctx):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "hermes_nous_runtime_disabled",
                "flag": FLAG_HERMES_NOUS_RUNTIME,
                "hint": "Enable feature flag hermes_nous_runtime for this tenant (test only).",
            },
        )


class ProvisionBody(BaseModel):
    runtime_base_url: str | None = Field(default=None, max_length=500)


class RunCreateBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    session_id: str | None = Field(default=None, max_length=200)
    tool_ids: list[str] = Field(default_factory=list, max_length=128)
    idempotency_key: str | None = Field(default=None, max_length=255)


@router.get("/status")
def nous_status(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    enabled = is_hermes_nous_enabled(db, ctx)
    runtime = tenant_runtime_record(db, ctx)
    return {
        "ok": True,
        "flag": FLAG_HERMES_NOUS_RUNTIME,
        "enabled": enabled,
        "engine": "nous_hermes_agent",
        "pin": "v0.23.1",
        "runtime": runtime,
        "diy_loop": "fallback_when_flag_off",
        "telephony": "not_in_scope",
    }


@router.post("/provision")
def nous_provision(
    body: ProvisionBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    record = ensure_tenant_hermes_home(db, ctx, runtime_base_url=body.runtime_base_url)
    return {"ok": True, "runtime": record}


@router.post("/runs")
def nous_create_run(
    body: RunCreateBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    try:
        return create_run(
            db,
            ctx,
            message=body.message,
            session_id=body.session_id,
            tool_ids=body.tool_ids or None,
            idempotency_key=body.idempotency_key,
        )
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


@router.get("/runs/{run_id}")
def nous_get_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    try:
        return get_run(db, ctx, run_id)
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


@router.post("/runs/{run_id}/stop")
def nous_stop_run(
    run_id: str,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    _require_flag(db, ctx)
    try:
        out = stop_run(db, ctx, run_id)
        revoke_run_token(db, ctx, run_id=run_id)
        return out
    except HermesBridgeError as exc:
        raise HTTPException(
            status_code=exc.status or 503,
            detail={"error": str(exc), "body": exc.body},
        ) from exc


class MintTokenBody(BaseModel):
    tool_ids: list[str] = Field(
        default_factory=lambda: ["get_knowledge", "office.health"],
        max_length=128,
    )


@router.post("/run-tokens")
def nous_mint_token(
    body: MintTokenBody,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict[str, Any]:
    """Dev/test helper: mint scoped MCP token without starting a Hermes process."""
    _require_flag(db, ctx)
    issued = issue_run_token(db, ctx, tool_ids=body.tool_ids)
    return {
        "ok": True,
        "token": issued.token,
        "run_id": issued.run_id,
        "expires_at": issued.expires_at,
        "tool_ids": issued.tool_ids,
    }
