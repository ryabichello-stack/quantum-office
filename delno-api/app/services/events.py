from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.platform_event import PlatformEvent

# E0.15 minimum operational event types
OPERATIONAL_EVENT_TYPES = frozenset(
    {
        "lead.created",
        "auth.failed",
        "auth.login",
        "operator.error",
        "knowledge.search_failed",
        "party.lookup",
        "party.lookup_failed",
        "party.enriched",
        "party.suggest",
        "party.suggest_failed",
    }
)


def emit_event(
    db: Session,
    *,
    event_type: str,
    category: str = "operational",
    tenant_id: UUID | None = None,
    source: str | None = None,
    payload: dict[str, Any] | None = None,
) -> PlatformEvent:
    """
    Persist a platform event. Payload always includes source + recorded_at when provided.
    tenant_id is stored on the row — never put another tenant's id in payload.
    """
    body: dict[str, Any] = dict(payload or {})
    if source is not None:
        body["source"] = source
    body.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())

    event = PlatformEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        category=category,
        payload=body,
    )
    db.add(event)
    db.flush()
    return event


def list_events_for_tenant(
    db: Session,
    tenant_id: UUID,
    *,
    event_type: str | None = None,
    limit: int = 100,
) -> list[PlatformEvent]:
    """Tenant-scoped event query — used by tests and future Supervisor/E6."""
    query = db.query(PlatformEvent).filter(PlatformEvent.tenant_id == tenant_id)
    if event_type:
        query = query.filter(PlatformEvent.event_type == event_type)
    return query.order_by(PlatformEvent.created_at.desc()).limit(min(limit, 500)).all()
