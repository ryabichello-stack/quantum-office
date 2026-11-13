"""Periodic Hermes tasks — parse + create + claim."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.services.agent_schedule import (
    claim_due_tasks,
    create_scheduled_task,
    parse_schedule_intent,
)


def test_parse_every_hour():
    out = parse_schedule_intent("проверяй заявки каждый час")
    assert out is not None
    assert out["every_minutes"] == 60
    assert "заявк" in out["goal"].lower()


def test_parse_every_15_min():
    out = parse_schedule_intent("мониторь почту каждые 15 минут")
    assert out is not None
    assert out["every_minutes"] == 15


def test_parse_rejects_plain_chat():
    assert parse_schedule_intent("подключи телеграм") is None
    assert parse_schedule_intent("какой баланс?") is None


def test_create_and_claim_due():
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="t", role="tenant_owner")
    fake = MagicMock()
    fake.id = uuid.uuid4()
    fake.trigger_config = {"every_minutes": 60}
    fake.status = "active"
    fake.trigger_kind = "schedule"
    fake.next_run_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    with patch("app.services.agent_schedule.create_task", return_value=fake) as ct:
        task = create_scheduled_task(db, ctx, goal="health", every_minutes=60)
        assert task is fake
        ct.assert_called_once()
        assert fake.next_run_at is not None

    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
        fake
    ]
    claimed = claim_due_tasks(db, limit=5)
    assert len(claimed) == 1
    db.commit.assert_called()
