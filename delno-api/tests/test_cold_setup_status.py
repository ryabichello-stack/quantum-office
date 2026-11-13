"""Cold tenant must not look «fully configured» via platform upstream flags."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import hermes_ops


def test_office_setup_status_hides_platform_configured_on_cold_tenant():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="fresh", role="tenant_owner")
    tenant = Tenant(slug="fresh", name="Fresh", settings={})
    tenant.id = tenant_id

    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value.one.return_value = tenant
    q.filter.return_value.count.return_value = 0
    q.filter.return_value.order_by.return_value.all.return_value = []

    connectors = {
        "tenant_slug": "fresh",
        "total": 3,
        "items": [
            {
                "kind": "mail",
                "enabled": False,
                "configured": True,
                "status": {
                    "ok": True,
                    "configured": True,
                    "message": "Mail upstream configured",
                    "enabled": False,
                },
            },
            {
                "kind": "calendar",
                "enabled": False,
                "configured": True,
                "status": {"ok": True, "configured": True, "enabled": False},
            },
            {
                "kind": "conference",
                "enabled": False,
                "configured": True,
                "status": {"ok": True, "configured": True, "enabled": False},
            },
        ],
    }
    readiness = [
        {
            "kind": "mail",
            "enabled": False,
            "usable": False,
            "reason": "not_enabled",
            "creds_policy": "tools_first",
        },
        {
            "kind": "calendar",
            "enabled": False,
            "usable": False,
            "reason": "not_enabled",
            "creds_policy": "tools_first",
        },
        {
            "kind": "conference",
            "enabled": False,
            "usable": False,
            "reason": "not_enabled",
            "creds_policy": "tools_first",
        },
    ]

    with (
        patch("app.services.hermes_ops.list_tenant_connectors", return_value=connectors),
        patch("app.services.hermes_ops.list_tenant_connector_readiness", return_value=readiness),
        patch("app.services.hermes_ops.list_secret_status", return_value={"items": []}),
        patch("app.services.hermes_ops.company_knowledge_ready", return_value={"ok": False, "detail": "need_company_profile"}),
        patch("app.services.sip_probe.probe_registration") as probe,
    ):
        probe.return_value = {
            "ok": True,
            "status": "registered",
            "message_ru": "Линия Mango Registered.",
        }
        status = hermes_ops.office_setup_status(db, ctx)

    assert status["setup_complete"] is False
    assert status["progress"]["required_done"] == 0
    for kind in ("mail", "calendar", "conference"):
        check = status["checks"][kind]
        assert check["ok"] is False
        detail = check["detail"]
        assert detail["tenant_usable"] is False
        assert detail["ok"] is False
        assert detail["configured"] is False
        assert "НЕ" in detail["summary_ru"] or "не" in detail["summary_ru"]
    phone = status["checks"]["phone"]["detail"]
    assert phone["registration_ok"] is False
    assert phone["sip_configured"] is False
    probe.assert_not_called()


def test_health_connectors_do_not_expose_platform_configured():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="fresh", role="tenant_owner")
    tenant = Tenant(slug="fresh", name="Fresh", settings={})
    tenant.id = tenant_id

    db = MagicMock()
    # office_health_report does several queries; keep them empty/cold.
    chain = db.query.return_value.filter.return_value
    chain.one.return_value = tenant
    chain.order_by.return_value.all.return_value = []
    chain.count.return_value = 0
    chain.all.return_value = []
    chain.limit.return_value.count.return_value = 0

    with (
        patch(
            "app.services.hermes_ops.list_tenant_connectors",
            return_value={"items": [{"kind": "mail", "enabled": False, "configured": True}]},
        ),
        patch(
            "app.services.hermes_ops.list_tenant_connector_readiness",
            return_value=[
                {"kind": "mail", "enabled": False, "usable": False, "reason": "not_enabled"},
            ],
        ),
        patch("app.services.hermes_ops.list_secret_status", return_value={"items": []}),
        patch("app.services.hermes_ops.emit_event"),
    ):
        health = hermes_ops.office_health_report(db, ctx)

    mail = health["connectors"][0]
    assert mail["configured"] is False
    assert mail["usable"] is False
    assert mail["ok"] is False
    assert "НЕ подключено" in mail["summary_ru"]
