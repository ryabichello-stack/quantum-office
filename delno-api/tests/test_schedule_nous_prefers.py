"""Scheduled tasks prefer Nous create_run when flag is on."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.models.agent_task import AgentTask
from app.models.tenant import Tenant
from app.services.agent_schedule import execute_scheduled_task
from app.services.hermes_nous.bridge import HermesBridgeError


def test_schedule_uses_nous_when_enabled():
    db = MagicMock()
    tenant = Tenant(slug="sched-co", name="Sched", settings={})
    tenant.id = uuid.uuid4()
    task = AgentTask(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        goal="проверяй заявки каждый час",
        trigger_kind="schedule",
        trigger_config={"every_minutes": 60},
        status="active",
    )
    db.query.return_value.filter.return_value.one_or_none.return_value = tenant

    with (
        patch("app.services.hermes_nous.flags.is_hermes_nous_enabled", return_value=True),
        patch(
            "app.services.hermes_nous.bridge.create_run",
            return_value={
                "ok": True,
                "output": "ok from nous",
                "run_id": "h1",
                "delno_agent_run_id": "d1",
            },
        ) as cr,
        patch("app.operator.agent.run_operator_turn") as diy,
    ):
        out = execute_scheduled_task(db, task)
        assert out["ok"] is True
        assert out["engine"] == "nous_hermes_agent"
        assert out["reply"] == "ok from nous"
        cr.assert_called_once()
        diy.assert_not_called()


def test_schedule_flag_on_unavailable_no_diy():
    db = MagicMock()
    tenant = Tenant(slug="sched-co2", name="Sched2", settings={})
    tenant.id = uuid.uuid4()
    task = AgentTask(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        goal="цель",
        trigger_kind="schedule",
        trigger_config={"every_minutes": 30},
        status="active",
    )
    db.query.return_value.filter.return_value.one_or_none.return_value = tenant

    with (
        patch("app.services.hermes_nous.flags.is_hermes_nous_enabled", return_value=True),
        patch(
            "app.services.hermes_nous.bridge.create_run",
            side_effect=HermesBridgeError("hermes_runtime_provisioning", status=503),
        ),
        patch("app.services.agent_schedule.record_run") as rec,
        patch("app.operator.agent.run_operator_turn") as diy,
    ):
        fake_run = MagicMock()
        fake_run.id = uuid.uuid4()
        rec.return_value = fake_run
        out = execute_scheduled_task(db, task)
        assert out["ok"] is False
        assert out["engine"] == "hermes_unavailable"
        diy.assert_not_called()
