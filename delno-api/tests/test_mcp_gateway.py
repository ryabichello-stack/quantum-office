import uuid
from unittest.mock import MagicMock

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.operator.tools import register_builtin_tools
from app.services.mcp_gateway import (
    build_hermes_profile,
    call_mcp_tool,
    ensure_mcp_api_key,
    find_tenant_by_mcp_key,
    mcp_tools_catalog,
    unwrap_for_http,
)


def test_mcp_catalog_includes_office_and_meta():
    register_builtin_tools()
    names = {t["name"] for t in mcp_tools_catalog()}
    assert "get_knowledge" in names
    assert "suggest_calendar_slots" in names
    assert "office.health" in names
    assert "office.connectors" in names
    assert "hermes.profile" in names
    assert len(names) >= 14


def test_ensure_and_find_mcp_key():
    tenant_id = uuid.uuid4()
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    key = ensure_mcp_api_key(db, tenant)
    assert key.startswith("dmcp_")
    assert tenant.settings["mcp_api_key"] == key
    # second call stable
    assert ensure_mcp_api_key(db, tenant) == key

    db.query.return_value.filter.return_value.filter.return_value.one_or_none.return_value = None
    db.query.return_value.filter.return_value.all.return_value = [tenant]
    found = find_tenant_by_mcp_key(db, key)
    assert found is tenant


def test_call_office_health_and_connectors(monkeypatch):
    register_builtin_tools()
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    monkeypatch.setattr("app.services.mcp_gateway.write_audit", lambda *a, **k: None)
    monkeypatch.setattr("app.services.mcp_gateway.emit_event", lambda *a, **k: None)

    health = call_mcp_tool(db, ctx, "office.health", {})
    assert health["ok"] is True
    assert health["tenant_slug"] == "demo"

    connectors = call_mcp_tool(db, ctx, "office.connectors", {})
    assert connectors["total"] == 4


def test_call_registry_stub_tool(monkeypatch):
    register_builtin_tools()
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    monkeypatch.setattr("app.services.mcp_gateway.write_audit", lambda *a, **k: None)
    monkeypatch.setattr("app.services.mcp_gateway.emit_event", lambda *a, **k: None)
    monkeypatch.setattr("app.operator.tools.office.write_audit", lambda *a, **k: None)

    out = call_mcp_tool(
        db,
        ctx,
        "suggest_calendar_slots",
        {"start": "2026-11-12T10:00:00+03:00"},
    )
    assert out.get("stub") is True or out.get("ok") is True
    wrapped = unwrap_for_http("suggest_calendar_slots", out)
    assert "tool" in wrapped


def test_hermes_profile_shape(monkeypatch):
    register_builtin_tools()
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="quantum-labs", role="tenant_owner")
    tenant = Tenant(slug="quantum-labs", name="Quantum Labs", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    profile = build_hermes_profile(db, ctx, include_mcp_key=True)
    assert profile["profile_kind"] == "hermes_tenant"
    assert profile["tenant_slug"] == "quantum-labs"
    assert profile["mcp"]["transport"] == "http"
    assert "/v1/mcp" in profile["mcp"]["base_url"]
    assert profile["mcp_api_key"].startswith("dmcp_")
    assert profile["toolset"]["total"] >= 14
