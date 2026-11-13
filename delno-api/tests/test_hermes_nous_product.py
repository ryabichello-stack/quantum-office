"""P1–P3 product loop unit tests (no live Hermes required)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.mcp_scope import filter_tools_catalog
from app.services.hermes_nous.onboarding import save_kb_draft, set_phase
from app.services.hermes_nous.tool_packs import ONBOARDING_KB, pack_for_mode


def _tenant():
    t = Tenant(slug="dogfood", name="Dogfood", settings={})
    t.id = uuid.uuid4()
    return t


def test_tool_packs_expand_by_mode():
    assert "upload_knowledge_snippet" in pack_for_mode("onboarding")
    # PRODUCT_LOOP: connectors (phone/DID) must be reachable before conduct mode.
    assert "phones.list" in pack_for_mode("onboarding")
    assert "phones.provision" in pack_for_mode("onboarding")
    assert "credentials.open_form" in pack_for_mode("onboarding")
    assert "office.connector_set" in pack_for_mode("onboarding")
    assert "generate_image" in pack_for_mode("onboarding")
    assert "send_mail_draft" in pack_for_mode("conduct")
    assert "outreach.stage_send" in pack_for_mode("tasks")
    assert len(pack_for_mode("tasks")) >= len(ONBOARDING_KB)


def test_onboarding_pack_filters_dangerous_when_empty_extra():
    catalog = [{"name": n} for n in list(ONBOARDING_KB) + ["send_mail_draft", "evil.tool"]]
    filtered = filter_tools_catalog(catalog, list(ONBOARDING_KB))
    names = {t["name"] for t in filtered}
    assert "upload_knowledge_snippet" in names
    assert "evil.tool" not in names


def test_kb_draft_and_phase(monkeypatch):
    tenant = _tenant()
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug="dogfood", role="tenant_owner")

    fake_setup = {
        "ok": True,
        "setup_complete": False,
        "checks": {"company_knowledge": {"ok": False}},
        "progress": {"required_done": 0, "required_total": 3},
        "message_ru": "нужен сетап",
    }
    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: fake_setup,
    )

    out = save_kb_draft(db, ctx, title="Компания", body="Мы делаем X", source_url="https://example.com")
    assert out["ok"] is True
    assert out["kb_draft"]["status"] == "draft"
    assert "example.com" in (out["kb_draft"].get("source_url") or "")

    phased = set_phase(db, ctx, "connectors")
    assert phased["phase"] == "connectors"
