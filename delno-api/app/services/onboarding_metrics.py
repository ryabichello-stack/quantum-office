"""O6 — TTFV milestones for conversation-driven onboarding."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.services.events import emit_event

MILESTONE_STARTED = "started"
MILESTONE_FIRST_EXTRACTION = "first_extraction"
MILESTONE_SUMMARY_READY = "summary_ready"
MILESTONE_PUBLISHED = "published"

TTFV_EVENT = "onboarding.ttfv_milestone"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _elapsed_ms(started_at: str | None, at: datetime | None = None) -> int | None:
    start = _parse_iso(started_at)
    if not start:
        return None
    end = at or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    return max(0, int((end - start).total_seconds() * 1000))


def get_ttfv_status(tenant: Tenant) -> dict[str, Any]:
    settings = tenant.settings if isinstance(tenant.settings, dict) else {}
    onboarding = settings.get("onboarding") if isinstance(settings.get("onboarding"), dict) else {}
    ttfv = settings.get("onboarding_ttfv") if isinstance(settings.get("onboarding_ttfv"), dict) else {}
    started_at = ttfv.get("started_at") or onboarding.get("started_at")
    milestones = dict(ttfv.get("milestones") or {})

    return {
        "started_at": started_at,
        "milestones": milestones,
        "elapsed_ms": {
            key: _elapsed_ms(started_at, _parse_iso(ts))
            for key, ts in milestones.items()
            if isinstance(ts, str)
        },
        "published": onboarding.get("status") == "published",
    }


def record_ttfv_milestone(
    db: Session,
    tenant: Tenant,
    milestone: str,
    *,
    tenant_id: UUID,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Record first occurrence of a TTFV milestone (idempotent per milestone)."""
    settings = dict(tenant.settings or {})
    ttfv = dict(settings.get("onboarding_ttfv") or {})
    milestones = dict(ttfv.get("milestones") or {})

    now = _utc_now_iso()
    settings = dict(tenant.settings or {})
    onboarding = settings.get("onboarding") if isinstance(settings.get("onboarding"), dict) else {}
    if not ttfv.get("started_at"):
        ttfv["started_at"] = onboarding.get("started_at") or now
    if milestone in milestones:
        return {"ok": True, "skipped": True, "milestone": milestone, "at": milestones[milestone]}

    milestones[milestone] = now
    ttfv["milestones"] = milestones
    settings["onboarding_ttfv"] = ttfv
    tenant.settings = settings

    started_at = ttfv.get("started_at")
    elapsed = _elapsed_ms(started_at, _parse_iso(now))
    payload: dict[str, Any] = {
        "milestone": milestone,
        "at": now,
        "elapsed_ms": elapsed,
        **(extra or {}),
    }
    emit_event(
        db,
        tenant_id=tenant_id,
        event_type=TTFV_EVENT,
        category="domain",
        source="onboarding.ttfv",
        payload=payload,
    )
    db.flush()
    return {"ok": True, "milestone": milestone, "at": now, "elapsed_ms": elapsed}
