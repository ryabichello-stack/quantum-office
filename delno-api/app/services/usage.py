from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.usage_record import UsageRecord


def record_usage(
    db: Session,
    *,
    tenant_id: UUID,
    metric: str,
    quantity: float = 1.0,
    meta: dict | None = None,
) -> UsageRecord:
    now = datetime.now(timezone.utc)
    row = UsageRecord(
        tenant_id=tenant_id,
        metric=metric,
        quantity=quantity,
        period_start=now,
        period_end=now,
        meta=meta or {},
    )
    db.add(row)
    db.flush()
    return row
