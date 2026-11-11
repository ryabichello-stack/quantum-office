import uuid
from unittest.mock import MagicMock

from app.adapters.connectors.calendar import CalendarConnector
from app.adapters.connectors.conference import ConferenceConnector
from app.adapters.connectors.files import FilesConnector
from app.adapters.connectors.mail import MailConnector
from app.adapters.connectors.registry import list_connectors
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.operator.tools.office import (
    CreateConferenceTool,
    ListFilesTool,
    SendMailDraftTool,
    SuggestCalendarSlotsTool,
)
from app.operator.tools.registry import ToolRegistry, tool_confirmation_class
from app.services.connectors import list_tenant_connectors, update_tenant_connector


def test_connector_registry_has_four():
    kinds = [c.kind for c in list_connectors()]
    assert kinds == ["mail", "calendar", "files", "conference"]


def test_mail_stub_send_draft():
    result = MailConnector().send_draft(
        tenant_slug="quantum-labs",
        config={},
        to="a@example.com",
        subject="Hi",
        body="Body",
    )
    assert result.ok is True
    assert result.configured is False
    assert result.error == "not_configured"
    assert result.data["stub"] is True


def test_calendar_stub_suggest():
    result = CalendarConnector().suggest_slots(
        tenant_slug="quantum-labs",
        config={},
        start="2026-11-12T10:00:00+03:00",
        duration_min=30,
    )
    assert result.ok is True
    assert result.data["count"] == 1
    assert result.data["stub"] is True


def test_files_stub_list():
    result = FilesConnector().list_entries(tenant_slug="demo", config={}, path="/docs")
    assert result.ok is True
    assert result.data["counts"]["total"] == 0


def test_conference_stub_create():
    result = ConferenceConnector().create(
        tenant_slug="demo",
        config={},
        title="Demo call",
        invitees=["a@b.c"],
    )
    assert result.ok is True
    assert "stub.delno.local" in result.data["join_url"]


def test_office_tools_registered_confirmation():
    assert tool_confirmation_class(SendMailDraftTool()) == "HIGH_IMPACT"
    assert tool_confirmation_class(CreateConferenceTool()) == "HIGH_IMPACT"
    assert tool_confirmation_class(SuggestCalendarSlotsTool()) == "READ"
    assert tool_confirmation_class(ListFilesTool()) == "READ"


def test_office_tools_run_stub(monkeypatch):
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    monkeypatch.setattr("app.operator.tools.office.write_audit", lambda *a, **k: None)

    cal = SuggestCalendarSlotsTool().run(db, ctx, start="2026-11-12T12:00:00+03:00")
    assert cal.ok is True
    assert cal.data["stub"] is True

    mail = SendMailDraftTool().run(db, ctx, to="x@y.z", subject="S", body="B")
    assert mail.ok is True
    assert mail.data["stub"] is True

    files = ListFilesTool().run(db, ctx, path="/")
    assert files.ok is True

    conf = CreateConferenceTool().run(db, ctx, title="Meet")
    assert conf.ok is True
    assert conf.data["stub"] is True


def test_list_and_enable_connector_service():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    listed = list_tenant_connectors(db, ctx)
    assert listed["total"] == 4
    assert all(item["configured"] is False for item in listed["items"])

    updated = update_tenant_connector(db, ctx, "calendar", enabled=True)
    assert updated["ok"] is True
    assert updated["enabled"] is True
    assert tenant.settings["connectors"]["calendar"]["enabled"] is True
    db.commit.assert_called()


def test_tool_registry_includes_office_tools():
    from app.operator.tools import register_builtin_tools
    from app.operator.tools.registry import registry

    # re-register into fresh registry for isolation
    reg = ToolRegistry()
    # use global register path
    register_builtin_tools()
    names = {t["name"] for t in registry.list_catalog()}
    assert "suggest_calendar_slots" in names
    assert "send_mail_draft" in names
    assert "list_files" in names
    assert "create_conference" in names
    assert len(names) >= 11
