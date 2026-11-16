"""DELNO-owned calendar. All channels use the same tenant-scoped records."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from sqlalchemy.orm import Session

from app.models.appointment import Appointment
from app.models.tenant import Tenant

ACTIVE = {"booked", "confirmed", "rescheduled"}


def parse_time(value: str, default_timezone: str | None = None) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        if not default_timezone:
            raise ValueError("timezone_required")
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(default_timezone))
        except KeyError as exc:
            raise ValueError("invalid_timezone") from exc
    return parsed.astimezone(timezone.utc)


def as_dict(row: Appointment) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "start": row.start_at.isoformat(),
        "end": row.end_at.isoformat(),
        "title": row.title,
        "email": row.contact_email or "",
        "phone": row.contact_phone or "",
        "status": row.status,
        "channel": row.channel,
        "external_user_id": row.external_user_id,
        "conference_url": row.conference_url or "",
        "sync_status": row.sync_status,
        "external_event_id": row.external_event_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def import_legacy(db: Session, tenant: Tenant) -> int:
    """Copy old settings appointments once; never remove original data."""
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    copied = 0
    for item in settings.get("appointments") or []:
        if not isinstance(item, dict) or not item.get("start"):
            continue
        try:
            identifier = uuid.UUID(str(item.get("id")))
        except (ValueError, TypeError):
            identifier = uuid.uuid5(uuid.NAMESPACE_URL, f"delno:{tenant.id}:{item.get('id') or item['start']}")
        if db.get(Appointment, identifier):
            continue
        try:
            start = parse_time(str(item["start"]), "Europe/Moscow")
            end = parse_time(str(item.get("end") or ""), "Europe/Moscow") if item.get("end") else start + timedelta(hours=1)
        except ValueError:
            continue
        db.add(Appointment(
            id=identifier, tenant_id=tenant.id, title=str(item.get("title") or "Встреча")[:240],
            start_at=start, end_at=end, status=str(item.get("status") or "booked"),
            contact_phone=str(item.get("phone") or "") or None,
            contact_email=str(item.get("email") or "") or None,
            channel=str(item.get("channel") or "legacy"),
            conference_url=str(item.get("conference_url") or "") or None,
            sync_status="legacy_unknown", meta={"legacy_id": item.get("id")},
        ))
        copied += 1
    if copied:
        db.flush()
    return copied


def list_rows(db: Session, tenant: Tenant, *, limit: int = 200) -> list[Appointment]:
    import_legacy(db, tenant)
    return (
        db.query(Appointment)
        .filter(Appointment.tenant_id == tenant.id)
        .order_by(Appointment.start_at.asc())
        .limit(limit)
        .all()
    )


def slot_free(db: Session, tenant: Tenant, start: datetime, end: datetime, *, excluding: uuid.UUID | None = None) -> bool:
    if end <= start:
        return False
    query = db.query(Appointment.id).filter(
        Appointment.tenant_id == tenant.id,
        Appointment.status.in_(ACTIVE),
        Appointment.start_at < end,
        Appointment.end_at > start,
    )
    if excluding:
        query = query.filter(Appointment.id != excluding)
    return query.first() is None


def create(
    db: Session, tenant: Tenant, *, start: datetime, end: datetime, title: str,
    phone: str | None = None, email: str | None = None, channel: str = "cabinet",
    external_user_id: str | None = None,
) -> Appointment:
    # Serialize bookings for the company, including when two channels submit at once.
    db.query(Tenant).filter(Tenant.id == tenant.id).with_for_update().one()
    import_legacy(db, tenant)
    if not slot_free(db, tenant, start, end):
        raise ValueError("slot_busy")
    row = Appointment(
        tenant_id=tenant.id, title=title[:240], start_at=start, end_at=end,
        contact_phone=phone, contact_email=email, channel=channel,
        external_user_id=external_user_id, status="booked", sync_status="local_only",
        sync_version=1, meta={},
    )
    db.add(row)
    db.flush()
    return row


def candidates(
    db: Session, tenant: Tenant, *, appointment_id: str | None = None,
    phone: str | None = None, channel: str | None = None,
    external_user_id: str | None = None,
) -> list[Appointment]:
    """IDs and caller-supplied email are never proof of access."""
    import_legacy(db, tenant)
    if not phone and not (channel in {"telegram", "max"} and external_user_id):
        return []
    query = db.query(Appointment).filter(Appointment.tenant_id == tenant.id, Appointment.status.in_(ACTIVE))
    if phone:
        query = query.filter(Appointment.contact_phone == phone)
    else:
        query = query.filter(Appointment.channel == channel, Appointment.external_user_id == external_user_id)
    if appointment_id:
        try:
            query = query.filter(Appointment.id == uuid.UUID(appointment_id))
        except ValueError:
            return []
    return query.order_by(Appointment.start_at.asc()).all()
