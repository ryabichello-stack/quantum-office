"""O4/O6 — website URL ingestion in onboarding."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.onboarding_website import GRACEFUL_FALLBACK, try_onboarding_url_ingest


def test_scenario_c_website_fail_returns_graceful_fallback():
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, slug="salon", name="Salon", public_key="pk", settings={})
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="salon", role="tenant_owner")
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    with patch("app.services.onboarding_website.fetch_website_content", side_effect=ValueError("fetch_failed")):
        with patch("app.services.onboarding_website.emit_event"):
            result = try_onboarding_url_ingest(db, ctx, "https://broken.example.ru")

    assert result is not None
    assert result["reply"] == GRACEFUL_FALLBACK
    assert "Ошибка" not in result["reply"]
    assert result["tool_calls"][0]["ok"] is False


def test_scenario_b_website_success_returns_draft():
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, slug="salon", name="Salon", public_key="pk", settings={})
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="salon", role="tenant_owner")
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    extracted = {
        "url": "https://example.ru/",
        "title": "Salon Example",
        "description": "Beauty salon",
        "paragraphs": ["We do nails and hair."] * 5,
        "sections": [{"heading": "Услуги", "level": "h2"}],
        "markdown": "# Salon\n\nУслуги маникюра и педикюра " + ("текст " * 30),
    }

    with patch("app.services.onboarding_website.fetch_website_content", return_value=extracted):
        with patch("app.services.onboarding_website.upsert_draft_knowledge", return_value={"ok": True, "document_id": "doc-1"}):
            with patch("app.services.onboarding_website.register_onboarding_draft_document_with_metrics"):
                with patch("app.services.onboarding_website.maybe_mark_summary_ready"):
                    with patch("app.services.onboarding_website.emit_event"):
                        result = try_onboarding_url_ingest(db, ctx, "https://example.ru")

    assert result is not None
    assert "Посмотрел сайт" in result["reply"]
    assert result["tool_calls"][0]["ok"] is True
