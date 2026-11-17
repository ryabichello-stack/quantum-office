"""Tenant calendar API; an external calendar is not required."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import calendar_store

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CreateAppointment(BaseModel):
    start: str
    end: str | None = None
    title: str = Field(min_length=1, max_length=240)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=255)


class ChangeAppointment(BaseModel):
    action: str = Field(pattern="^(reschedule|confirm|cancel)$")
    start: str | None = None
    end: str | None = None


def _tenant(db: Session, ctx: TenantContext) -> Tenant:
    return db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()


@router.get("/appointments")
def list_appointments(
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    rows = calendar_store.list_rows(db, _tenant(db, ctx), limit=limit)
    db.commit()
    return {"items": [calendar_store.as_dict(row) for row in rows]}


@router.post("/appointments")
def create_appointment(
    body: CreateAppointment,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    from app.services.meeting_flow import handle as handle_meeting

    result = handle_meeting(
        db, ctx, "book_meeting", body.model_dump(exclude_none=True), "cabinet",
    )
    if not result.get("booked"):
        raise HTTPException(status_code=409 if result.get("error") == "slot_busy" else 422, detail=result)
    return result


@router.patch("/appointments/{appointment_id}")
def change_appointment(
    appointment_id: uuid.UUID,
    body: ChangeAppointment,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    from app.services.meeting_flow import handle as handle_meeting

    action = {"reschedule": "reschedule_meeting", "confirm": "confirm_meeting", "cancel": "cancel_meeting"}[body.action]
    result = handle_meeting(db, ctx, action, {"appointment_id": str(appointment_id), **body.model_dump(exclude_none=True)}, "cabinet")
    if not result.get("ok"):
        raise HTTPException(status_code=404 if result.get("error") == "appointment_not_found_or_unverified" else 409, detail=result)
    return result
