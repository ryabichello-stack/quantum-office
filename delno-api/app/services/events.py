from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.platform_event import PlatformEvent


def emit_event(
    db: Session,
    *,
    event_type: str,
    category: str = "operational",
    tenant_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> PlatformEvent:
    event = PlatformEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        category=category,
        payload=payload or {},
    )
    db.add(event)
    db.flush()
    return event
