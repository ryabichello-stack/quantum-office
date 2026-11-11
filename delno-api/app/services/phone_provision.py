"""Provision DID numbers for a tenant (Hermes first-time setup + admin)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.phone_number import PhoneNumber
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.telephony import normalize_e164


def list_phones(db: Session, ctx: TenantContext) -> dict[str, Any]:
    rows = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.tenant_id == ctx.tenant_id)
        .order_by(PhoneNumber.created_at.desc())
        .all()
    )
    return {
        "ok": True,
        "items": [
            {
                "id": str(r.id),
                "e164": r.e164,
                "label": r.label,
                "status": r.status,
                "routing_config": r.routing_config or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


def provision_phone(
    db: Session,
    ctx: TenantContext,
    *,
    e164: str,
    label: str | None = None,
    status: str = "active",
    routing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    e164_n = normalize_e164(e164)
    if len(e164_n) < 10:
        return {"ok": False, "error": "invalid_e164"}

    clash = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.e164 == e164_n, PhoneNumber.status == "active")
        .one_or_none()
    )
    if clash and clash.tenant_id != ctx.tenant_id:
        return {"ok": False, "error": "did_owned_by_other_tenant"}

    row = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.tenant_id == ctx.tenant_id, PhoneNumber.e164 == e164_n)
        .one_or_none()
    )
    if row:
        row.label = label or row.label
        row.status = status
        if routing_config is not None:
            row.routing_config = routing_config
    else:
        row = PhoneNumber(
            tenant_id=ctx.tenant_id,
            e164=e164_n,
            label=label or "main",
            status=status,
            routing_config=routing_config or {"frontline": True, "outbound": True},
        )
        db.add(row)
    db.flush()
    write_audit(
        db,
        ctx,
        action="phone.provision",
        resource=f"phone:{e164_n}",
        new_value={"status": status, "label": row.label},
        actor="hermes",
    )
    emit_event(
        db,
        event_type="phone.provisioned",
        category="domain",
        tenant_id=ctx.tenant_id,
        source="hermes",
        payload={"e164": e164_n, "status": status},
    )
    db.commit()
    return {
        "ok": True,
        "phone": {
            "id": str(row.id),
            "e164": row.e164,
            "label": row.label,
            "status": row.status,
            "routing_config": row.routing_config or {},
        },
    }


def set_phone_status(
    db: Session,
    ctx: TenantContext,
    phone_id: uuid.UUID,
    *,
    status: str,
) -> dict[str, Any]:
    row = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.id == phone_id, PhoneNumber.tenant_id == ctx.tenant_id)
        .one_or_none()
    )
    if not row:
        return {"ok": False, "error": "not_found"}
    old = row.status
    row.status = status
    write_audit(
        db,
        ctx,
        action="phone.status",
        resource=f"phone:{row.e164}",
        old_value={"status": old},
        new_value={"status": status},
        actor="hermes",
    )
    db.commit()
    return {"ok": True, "id": str(row.id), "e164": row.e164, "status": status}
