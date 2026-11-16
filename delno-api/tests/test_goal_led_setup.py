"""A company chooses its goals and connectors; no universal setup sequence."""

import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_ops import acknowledge_new_instruments, office_health_report, office_setup_status, set_owner_goal
from app.services.instrument_catalog import Instrument, register_instrument, unregister_instrument


def _tenant():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="goal-led", name="Goal Led", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    return db, TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")


def _status(db, ctx):
    with (
        patch("app.services.hermes_ops.list_tenant_connectors", return_value={"items": []}),
        patch("app.services.hermes_ops.list_tenant_connector_readiness", return_value=[]),
        patch("app.services.hermes_ops.list_secret_status", return_value={"items": []}),
        patch("app.services.hermes_ops.company_knowledge_ready", return_value={"ok": False}),
    ):
        return office_setup_status(db, ctx)


def test_cold_company_has_no_mandatory_tools():
    db, ctx = _tenant()
    try:
        status = _status(db, ctx)
        assert status["next_steps"] == []
        assert status["progress"]["required_total"] == 0
        assert all(check["optional"] for check in status["checks"].values())
        assert status["setup_complete"] is False
    finally:
        db.close()


def test_goal_without_connectors_is_ready_and_phone_is_not_suggested():
    db, ctx = _tenant()
    try:
        with patch("app.services.hermes_ops.office_setup_status", side_effect=lambda db_, ctx_: _status(db_, ctx_)):
            saved = set_owner_goal(db, ctx, goal="Сделать исследование рынка", requested_instruments=[])
        assert saved["goal"] == "Сделать исследование рынка"
        status = _status(db, ctx)
        assert status["setup_complete"] is True
        assert status["next_steps"] == []
        assert not status["checks"]["phone"]["ok"]
        with (
            patch("app.services.hermes_ops.list_tenant_connectors", return_value={"items": []}),
            patch("app.services.hermes_ops.list_tenant_connector_readiness", return_value=[]),
            patch("app.services.hermes_ops.list_secret_status", return_value={"items": []}),
        ):
            health = office_health_report(db, ctx)
        assert not any(item["code"].startswith("phone.") for item in health["alerts"])
    finally:
        db.close()


def test_only_chosen_connectors_are_offered_and_new_tool_is_discoverable():
    db, ctx = _tenant()
    try:
        with patch("app.services.hermes_ops.office_setup_status", side_effect=lambda db_, ctx_: _status(db_, ctx_)):
            set_owner_goal(db, ctx, goal="Отвечать на сообщения", requested_instruments=["telegram"])
        register_instrument(Instrument(id="whatsapp", title="WhatsApp", hint="Подключить канал", order=55))
        assert [s["id"] for s in _status(db, ctx)["new_instruments"]] == ["whatsapp"]
        with patch("app.services.hermes_ops.office_setup_status", side_effect=lambda db_, ctx_: _status(db_, ctx_)):
            saved = set_owner_goal(db, ctx, goal="Отвечать на сообщения", requested_instruments=["telegram", "whatsapp"])
        assert [s["id"] for s in saved["next_steps"]] == ["telegram", "whatsapp"]
        assert "phone" not in [s["id"] for s in saved["next_steps"]]
        assert "whatsapp" in [i["id"] for i in saved["instruments"]["platform"]]
        with patch("app.services.hermes_ops.office_setup_status", side_effect=lambda db_, ctx_: _status(db_, ctx_)):
            acknowledged = acknowledge_new_instruments(db, ctx, ["whatsapp"])
        assert acknowledged["new_instruments"] == []
    finally:
        unregister_instrument("whatsapp")
        db.close()
