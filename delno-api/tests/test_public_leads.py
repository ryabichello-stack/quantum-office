"""P1.4 — public leads API writes to PostgreSQL (handler unit test)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.api.v1.public import PublicLeadCreate, create_public_lead
from app.models.lead import Lead
from app.services.channel_router import ChannelContext


def test_create_public_lead_persists_to_db():
    tenant_id = uuid.uuid4()
    mock_db = MagicMock()
    channel = ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="delno-demo",
        channel_type="website",
        principal_id="service:delno-widget-guest",
    )
    fake_lead = Lead(
        tenant_id=tenant_id,
        name="Иван Тестов",
        phone="+79991234567",
        email="ivan@example.com",
        company="ООО Тест",
        source="Сайт DELNO",
    )
    fake_lead.id = uuid.uuid4()

    with patch("app.api.v1.public.resolve_public_lead", return_value=channel):
        with patch(
            "app.api.v1.public.create_lead_record",
            return_value=(fake_lead, {"telegram_notified": False, "enrichment": {"enriched": False}}),
        ) as mock_create:
            with patch("app.api.v1.public.record_usage"):
                result = create_public_lead(
                    PublicLeadCreate(
                        name="Иван Тестов",
                        phone="+79991234567",
                        email="ivan@example.com",
                        company="ООО Тест",
                        source="Сайт DELNO",
                    ),
                    db=mock_db,
                    x_tenant_slug="delno-demo",
                )

    assert result["ok"] is True
    assert result["lead_id"] == str(fake_lead.id)
    assert result["party_enriched"] is False
    mock_create.assert_called_once()
    kwargs = mock_create.call_args.kwargs
    assert kwargs["name"] == "Иван Тестов"
    assert kwargs["phone"] == "+79991234567"
    assert kwargs["source"] == "Сайт DELNO"
    assert kwargs["event_source"] == "public.leads"
    mock_db.commit.assert_called_once()


def test_create_public_lead_unknown_tenant():
    from fastapi import HTTPException

    mock_db = MagicMock()
    with patch("app.api.v1.public.resolve_public_lead", return_value=None):
        try:
            create_public_lead(
                PublicLeadCreate(name="A", phone="+79991234567"),
                db=mock_db,
                x_tenant_slug="missing-tenant",
            )
            assert False, "expected HTTPException"
        except HTTPException as exc:
            assert exc.status_code == 404
    mock_db.commit.assert_not_called()
