"""O6 — onboarding scenarios A–E (unit-level with mocks)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.onboarding_summary import (
    build_onboarding_summary,
    register_onboarding_draft_document,
    try_onboarding_summary_reply,
)


def test_scenario_a_conversation_builds_draft_summary():
    """A — только разговор: текст → draft → summary."""
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="repair-co",
        name="Repair Co",
        public_key="pk",
        settings={"onboarding": {"status": "in_progress"}},
    )
    body = (
        "# Repair Co\n\nМы занимаемся ремонтом кондиционеров.\n\n"
        "Выезд по Москве. Контакты: +7 999 000-00-00 repair@test.ru\n"
        + ("описание услуг " * 25)
    )
    register_onboarding_draft_document(
        tenant,
        document_id="doc-conv",
        title="Разговор",
        body=body,
        source_type="conversation",
        source_label="onboarding.chat",
    )
    summary = build_onboarding_summary(tenant)
    assert summary["profile"]["company_name"] == "Repair Co"
    assert summary["document_ids"] == ["doc-conv"]


def test_scenario_a_confirm_publishes_when_enough_data():
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug="repair-co",
        name="Repair Co",
        public_key="pk",
        settings={
            "onboarding": {"status": "summary_ready"},
            "onboarding_draft": {
                "documents": {
                    "doc-1": {
                        "title": "Biz",
                        "body": "# Repair\n\n" + ("ремонт кондиционеров " * 30),
                        "source_type": "conversation",
                        "source_label": "chat",
                    }
                }
            },
        },
    )
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="repair-co", role="tenant_owner")
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    with patch("app.services.onboarding_summary.publish_onboarding_from_summary") as mock_publish:
        mock_publish.return_value = {"ok": True, "message": "Готово. Теперь я могу отвечать вашим клиентам."}
        reply = try_onboarding_summary_reply(db, ctx, "Всё верно")

    assert reply is not None
    assert "Готово" in reply["reply"]
    mock_publish.assert_called_once()


def test_scenario_e_conflict_then_numeric_reply():
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug="salon",
        name="Salon",
        public_key="pk",
        settings={
            "onboarding_draft": {
                "documents": {
                    "d1": {
                        "title": "web",
                        "body": "Маникюр 1500 руб\n" + ("x " * 40),
                        "source_type": "website",
                        "source_label": "site",
                    },
                    "d2": {
                        "title": "file",
                        "body": "Маникюр 1800 руб\n" + ("y " * 40),
                        "source_type": "file",
                        "source_label": "price.xlsx",
                    },
                }
            }
        },
    )
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="salon", role="tenant_owner")
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    with patch("app.services.onboarding_summary.resolve_onboarding_conflict") as mock_resolve:
        with patch("app.services.onboarding_summary.build_onboarding_summary") as mock_summary:
            mock_summary.return_value = {"profile": {}, "missing_fields": [], "conflicts": []}
            reply = try_onboarding_summary_reply(db, ctx, "1800")

    assert reply is not None
    assert "1800" in reply["reply"]
    mock_resolve.assert_called_once()
