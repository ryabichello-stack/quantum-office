"""Telephony bridge API — Asterisk/Dialer ↔ Frontline (webhook token)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.config import get_settings
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.services import hermes_ops, telephony

router = APIRouter(prefix="/telephony", tags=["telephony"])


def _require_telephony_token(
    x_telephony_token: str | None = Header(default=None, alias="X-Telephony-Token"),
    x_webhook_token: str | None = Header(default=None, alias="X-Webhook-Token"),
) -> None:
    settings = get_settings()
    expected = (settings.telephony_webhook_token or settings.office_webhook_token or "").strip()
    if not expected:
        # Dev-friendly: allow if unset, but prefer configured token in prod
        return
    got = (x_telephony_token or x_webhook_token or "").strip()
    if got != expected:
        raise HTTPException(status_code=401, detail="unauthorized")


class InboundStartRequest(BaseModel):
    did: str = Field(min_length=5, max_length=20)
    from_number: str = Field(min_length=5, max_length=20)
    external_id: str | None = Field(default=None, max_length=120)
    meta: dict = Field(default_factory=dict)


class CallEndRequest(BaseModel):
    session_id: UUID
    transcript: str | None = None
    summary: str | None = None
    outcome: str | None = Field(default=None, max_length=64)
    duration_sec: int | None = None


class CallTurnRequest(BaseModel):
    session_id: UUID
    text: str = Field(min_length=1, max_length=8000)


class DialRequest(BaseModel):
    to_e164: str = Field(min_length=5, max_length=20)
    script: str = Field(default="", max_length=8000)
    lead_id: UUID | None = None


@router.post("/inbound/start")
def telephony_inbound_start(
    body: InboundStartRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_telephony_token),
) -> dict:
    out = telephony.start_inbound_call(
        db,
        did=body.did,
        from_number=body.from_number,
        external_id=body.external_id,
        meta=body.meta,
    )
    if not out.get("ok"):
        code = 404 if out.get("error") == "did_not_provisioned" else 400
        raise HTTPException(status_code=code, detail=out.get("error"))
    return out


@router.post("/calls/end")
def telephony_call_end(
    body: CallEndRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_telephony_token),
) -> dict:
    out = telephony.end_call(
        db,
        session_id=body.session_id,
        transcript=body.transcript,
        summary=body.summary,
        outcome=body.outcome,
        duration_sec=body.duration_sec,
    )
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("error"))
    return out


@router.post("/calls/turn")
def telephony_call_turn(
    body: CallTurnRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_telephony_token),
) -> dict:
    out = telephony.frontline_turn(db, session_id=body.session_id, text=body.text)
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error"))
    return out


@router.post("/jobs/claim")
def telephony_jobs_claim(
    db: Session = Depends(get_db),
    _: None = Depends(_require_telephony_token),
) -> dict:
    """Dialer worker claims next queued outbound job."""
    out = telephony.claim_next_job(db)
    if not out:
        return {"ok": True, "job": None}
    return {"ok": True, **out}


@router.get("/jobs/next")
def telephony_jobs_peek(
    db: Session = Depends(get_db),
    _: None = Depends(_require_telephony_token),
) -> dict:
    # Non-locking peek for monitoring
    from app.models.call_job import CallJob

    job = (
        db.query(CallJob)
        .filter(CallJob.status == "queued")
        .order_by(CallJob.priority.asc(), CallJob.created_at.asc())
        .first()
    )
    return {"ok": True, "job": telephony.job_to_dict(job) if job else None}


# Owner / Hermes authenticated endpoints
@router.get("/sessions")
def telephony_sessions(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = 30,
) -> dict:
    return {"ok": True, "items": telephony.list_sessions(db, ctx, limit=limit)}


@router.post("/dial")
def telephony_dial(
    body: DialRequest,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    out = telephony.create_outbound_job(
        db,
        ctx,
        to_e164=body.to_e164,
        script=body.script,
        lead_id=body.lead_id,
        created_by="owner",
    )
    if not out.get("ok"):
        raise HTTPException(status_code=400, detail=out.get("error"))
    return out


@router.get("/hermes/setup")
def hermes_setup(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    return hermes_ops.office_setup_status(db, ctx)


@router.get("/hermes/health")
def hermes_health(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    return hermes_ops.office_health_report(db, ctx)
