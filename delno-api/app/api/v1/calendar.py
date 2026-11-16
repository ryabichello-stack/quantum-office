"""Tenant calendar API; an external calendar is not required."""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.appointment import Appointment
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
    try:
        start = calendar_store.parse_time(body.start)
        end = calendar_store.parse_time(body.end) if body.end else start + timedelta(hours=1)
        row = calendar_store.create(
            db, _tenant(db, ctx), start=start, end=end, title=body.title,
            phone=body.phone, email=body.email,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409 if str(exc) == "slot_busy" else 422, detail=str(exc)) from exc
    return {"ok": True, "appointment": calendar_store.as_dict(row)}


@router.patch("/appointments/{appointment_id}")
def change_appointment(
    appointment_id: uuid.UUID,
    body: ChangeAppointment,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    tenant = _tenant(db, ctx)
    row = db.query(Appointment).filter(
        Appointment.id == appointment_id, Appointment.tenant_id == ctx.tenant_id,
    ).with_for_update().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="appointment_not_found")
    if row.status == "cancelled":
        raise HTTPException(status_code=409, detail="appointment_cancelled")
    if body.action == "reschedule":
        if not body.start:
            raise HTTPException(status_code=422, detail="start_required")
        try:
            start = calendar_store.parse_time(body.start)
            end = calendar_store.parse_time(body.end) if body.end else start + (row.end_at - row.start_at)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not calendar_store.slot_free(db, tenant, start, end, excluding=row.id):
            raise HTTPException(status_code=409, detail="slot_busy")
        row.start_at, row.end_at, row.status = start, end, "rescheduled"
    else:
        row.status = "confirmed" if body.action == "confirm" else "cancelled"
    row.sync_version += 1
    row.sync_status = "pending" if row.external_event_id else "local_only"
    db.add(row)
    db.commit()
    return {"ok": True, "appointment": calendar_store.as_dict(row)}
