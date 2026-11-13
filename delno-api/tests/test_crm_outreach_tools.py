"""CRM-lite + outreach staging tools (tools-first, no external creds)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.adapters.connectors.outreach import OutreachConnector
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.models.tenant import Tenant
from app.operator.tools import register_builtin_tools
from app.operator.tools.crm import (
    CrmCompanyUpsertTool,
    CrmFunnelTool,
    CrmLifecycleSetTool,
    CrmSuggestNextTool,
)
from app.operator.tools.outreach import OutreachPreviewTool, OutreachStageSendTool
from app.operator.tools.registry import tool_confirmation_class
from app.services import crm as crm_service
from app.services.mcp_gateway import call_mcp_tool, mcp_tools_catalog


def _ctx(tenant_id: uuid.UUID | None = None) -> TenantContext:
    return TenantContext(
        tenant_id=tenant_id or uuid.uuid4(),
        tenant_slug="demo",
        role="tenant_owner",
    )


def test_outreach_stub_preview_and_stage():
    conn = OutreachConnector()
    preview = conn.preview(tenant_slug="demo", config={}, to="a@b.ru", company="Acme")
    assert preview.ok is True
    assert preview.data["stub"] is True
    assert "Acme" in preview.data["subject"] or "Acme" in preview.data["body"]

    staged = conn.stage_send(tenant_slug="demo", config={}, to="a@b.ru", company="Acme")
    assert staged.ok is True
    assert staged.data["staged"] is True
    assert staged.data["sent"] is False
    assert staged.data["dry_run"] is True


def test_crm_normalize_and_funnel(monkeypatch):
    tenant_id = uuid.uuid4()
    ctx = _ctx(tenant_id)
    lead = Lead(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Ivan",
        phone="+7999",
        company="Acme",
        status="new",
        party_json={"inn": "1"},
        created_at=datetime.now(timezone.utc),
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [lead]
    out = crm_service.funnel_counts(db, ctx)
    assert out["total"] == 1
    assert out["stages"]["ENRICHED"] == 1


def test_crm_lifecycle_set(monkeypatch):
    tenant_id = uuid.uuid4()
    ctx = _ctx(tenant_id)
    lead = Lead(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Ivan",
        phone="+7999",
        status="NEW",
    )
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = lead
    monkeypatch.setattr("app.services.crm.write_audit", lambda *a, **k: None)
    monkeypatch.setattr("app.services.crm.emit_event", lambda *a, **k: None)
    out = crm_service.set_lifecycle(db, ctx, lead_id=str(lead.id), status="MEETING")
    assert out["ok"] is True
    assert lead.status == "MEETING"


def test_crm_tools_confirmation_classes():
    assert tool_confirmation_class(CrmFunnelTool()) == "READ"
    assert tool_confirmation_class(CrmSuggestNextTool()) == "READ"
    assert tool_confirmation_class(CrmLifecycleSetTool()) == "HIGH_IMPACT"
    assert tool_confirmation_class(CrmCompanyUpsertTool()) == "HIGH_IMPACT"
    assert tool_confirmation_class(OutreachStageSendTool()) == "HIGH_IMPACT"
    assert tool_confirmation_class(OutreachPreviewTool()) == "READ"


def test_mcp_call_crm_and_outreach(monkeypatch):
    register_builtin_tools()
    names = {t["name"] for t in mcp_tools_catalog()}
    assert "crm.funnel" in names
    assert "outreach.dashboard" in names

    tenant_id = uuid.uuid4()
    ctx = _ctx(tenant_id)
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    db.query.return_value.filter.return_value.all.return_value = []

    monkeypatch.setattr("app.services.mcp_gateway.write_audit", lambda *a, **k: None)
    monkeypatch.setattr("app.services.mcp_gateway.emit_event", lambda *a, **k: None)
    monkeypatch.setattr("app.operator.tools.outreach.write_audit", lambda *a, **k: None)

    funnel = call_mcp_tool(db, ctx, "crm.funnel", {})
    assert funnel.get("ok") is True
    assert "stages" in funnel

    packs = call_mcp_tool(db, ctx, "outreach.packs", {})
    assert packs.get("ok") is True
    assert packs.get("stub") is True or (packs.get("packs") and len(packs["packs"]) >= 1)

    preview = call_mcp_tool(db, ctx, "outreach.preview", {"to": "x@y.ru", "company": "Beta"})
    assert preview.get("ok") is True
    assert preview.get("stub") is True
