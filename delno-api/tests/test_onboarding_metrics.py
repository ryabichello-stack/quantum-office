"""O6 — TTFV milestone tracking."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.tenant import Tenant
from app.services.onboarding_metrics import (
    MILESTONE_FIRST_EXTRACTION,
    MILESTONE_STARTED,
    get_ttfv_status,
    record_ttfv_milestone,
)


def test_record_ttfv_milestone_idempotent():
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug="salon",
        name="Salon",
        public_key="pk",
        settings={"onboarding": {"started_at": "2026-09-05T10:00:00+00:00"}},
    )
    db = MagicMock()

    with patch("app.services.onboarding_metrics.emit_event") as mock_emit:
        first = record_ttfv_milestone(db, tenant, MILESTONE_STARTED, tenant_id=tenant_id)
        second = record_ttfv_milestone(db, tenant, MILESTONE_STARTED, tenant_id=tenant_id)

    assert first["ok"] is True
    assert second.get("skipped") is True
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "onboarding.ttfv_milestone"


def test_get_ttfv_status_returns_milestones():
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="salon",
        name="Salon",
        public_key="pk",
        settings={
            "onboarding": {"started_at": "2026-09-05T10:00:00+00:00", "status": "in_progress"},
            "onboarding_ttfv": {
                "started_at": "2026-09-05T10:00:00+00:00",
                "milestones": {
                    MILESTONE_STARTED: "2026-09-05T10:00:00+00:00",
                    MILESTONE_FIRST_EXTRACTION: "2026-09-05T10:01:30+00:00",
                },
            },
        },
    )
    status = get_ttfv_status(tenant)
    assert status["milestones"][MILESTONE_FIRST_EXTRACTION]
    assert status["elapsed_ms"][MILESTONE_FIRST_EXTRACTION] == 90000
