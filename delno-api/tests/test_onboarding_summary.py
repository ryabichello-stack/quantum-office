"""O5/O6 — summary, conflicts, publish."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.onboarding_summary import (
    build_onboarding_summary,
    detect_price_conflicts,
    publish_onboarding_from_summary,
    register_onboarding_draft_document,
    resolve_onboarding_conflict,
    try_onboarding_summary_reply,
)


@pytest.fixture
def tenant_with_conflict():
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug="salon-demo",
        name="Salon Demo",
        public_key="pk",
        settings={
            "onboarding": {"status": "in_progress", "started_at": "2026-09-05T10:00:00+00:00"},
            "onboarding_draft": {
                "documents": {
                    "doc-web": {
                        "title": "Site",
                        "body": "Маникюр 1500 руб\nПедикюр 2000 руб\n" + ("описание услуг " * 20),
                        "source_type": "website",
                        "source_label": "https://example.ru",
                    },
                    "doc-file": {
                        "title": "Price",
                        "body": "Маникюр 1800 руб\nПедикюр 2000 руб\n" + ("прайс услуг " * 20),
                        "source_type": "file",
                        "source_label": "price.xlsx",
                    },
                }
            },
        },
    )
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="salon-demo", role="tenant_owner", user_id=uuid.uuid4())
    return tenant, ctx


def test_detect_price_conflicts_scenario_e(tenant_with_conflict):
    tenant, _ctx = tenant_with_conflict
    draft = tenant.settings["onboarding_draft"]
    conflicts = detect_price_conflicts(draft)
    assert len(conflicts) >= 1
    manicure = next(c for c in conflicts if "маник" in c["label"].lower())
    prices = {v["price"] for v in manicure["values"]}
    assert prices == {1500, 1800}


def test_publish_blocked_with_unresolved_conflicts(tenant_with_conflict):
    tenant, ctx = tenant_with_conflict
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    result = publish_onboarding_from_summary(db, ctx, approved_by="user:test")
    assert result["ok"] is False
    assert result["error"] == "unresolved_conflicts"


def test_confirm_message_asks_about_conflict(tenant_with_conflict):
    tenant, ctx = tenant_with_conflict
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    reply = try_onboarding_summary_reply(db, ctx, "Всё верно")
    assert reply is not None
    assert "1500" in reply["reply"] or "1800" in reply["reply"]
    assert "актуальна" in reply["reply"].lower()


def test_resolve_conflict_allows_summary_ready(tenant_with_conflict):
    tenant, ctx = tenant_with_conflict
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant
    draft = tenant.settings["onboarding_draft"]
    conflicts = detect_price_conflicts(draft)
    field = conflicts[0]["field"]

    with patch("app.services.onboarding_summary.emit_event"):
        with patch("app.services.onboarding_summary.maybe_mark_summary_ready"):
            resolve_onboarding_conflict(db, tenant, field=field, canonical_value=1800)

    canonical = tenant.settings["onboarding_draft"]["canonical"]
    assert canonical[field] == 1800
    assert detect_price_conflicts(tenant.settings["onboarding_draft"]) == []


def test_build_onboarding_summary_has_profile(tenant_with_conflict):
    tenant, _ctx = tenant_with_conflict
    summary = build_onboarding_summary(tenant)
    assert summary["profile"]["company_name"] == "Salon Demo"
    assert summary["sources_count"] == 2
    assert summary["document_ids"]


def test_publish_succeeds_after_canonical_set(tenant_with_conflict):
    tenant, ctx = tenant_with_conflict
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    draft = tenant.settings["onboarding_draft"]
    conflicts = detect_price_conflicts(draft)
    tenant.settings["onboarding_draft"]["canonical"] = {conflicts[0]["field"]: 1800}

    with patch("app.services.onboarding_summary.publish_tenant_knowledge_document") as mock_pub:
        mock_pub.return_value = {"ok": True, "document_id": "doc-x"}
        with patch("app.services.onboarding_summary.emit_event"):
            with patch("app.services.onboarding_summary.record_ttfv_milestone"):
                result = publish_onboarding_from_summary(db, ctx, approved_by="user:test")

    assert result["ok"] is True
    assert "Готово" in result["message"]
    assert tenant.settings["onboarding"]["status"] == "published"
