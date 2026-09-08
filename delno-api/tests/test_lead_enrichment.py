"""E1.13 — lead INN enrichment on create."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.operator.tools.builtin import CreateLeadTool, LookupCompanyByInnTool
from app.services.leads import create_lead_record
from app.services.party_enrichment import enrich_lead_from_inn

SAMPLE_LOOKUP = {
    "ok": True,
    "cached": True,
    "inn": "471405233378",
    "flat": {"company_name": "ИП Рябов Денис Вадимович", "inn": "471405233378"},
    "party": {"company_name": "ИП Рябов Денис Вадимович"},
}


def test_enrich_lead_sets_party_json_and_company():
    tenant_id = uuid.uuid4()
    db = MagicMock()
    lead = Lead(
        tenant_id=tenant_id,
        name="Test",
        phone="+79990001122",
        source="website",
    )
    lead.id = uuid.uuid4()

    with patch("app.services.party_enrichment.lookup_party_by_inn", return_value=SAMPLE_LOOKUP):
        with patch("app.services.party_enrichment.emit_event") as mock_emit:
            result = enrich_lead_from_inn(db, lead, "471405233378", tenant_id=tenant_id)

    assert result["enriched"] is True
    assert lead.inn == "471405233378"
    assert lead.company == "ИП Рябов Денис Вадимович"
    assert lead.party_json["flat"]["company_name"] == "ИП Рябов Денис Вадимович"
    assert lead.party_enriched_at is not None
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "party.enriched"


def test_enrich_lead_skips_invalid_inn():
    tenant_id = uuid.uuid4()
    lead = Lead(tenant_id=tenant_id, name="T", phone="1", source="web")
    db = MagicMock()
    result = enrich_lead_from_inn(db, lead, "bad", tenant_id=tenant_id)
    assert result["enriched"] is False


def test_create_lead_record_with_inn():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    db = MagicMock()

    def capture_add(obj):
        if isinstance(obj, Lead):
            obj.id = uuid.uuid4()

    db.add.side_effect = capture_add
    db.flush = MagicMock()

    with patch("app.services.leads.enrich_lead_from_inn", return_value={"enriched": True}) as mock_enrich:
        with patch("app.services.leads.notify_lead_telegram", return_value=False):
            with patch("app.services.leads.write_audit"):
                with patch("app.services.leads.emit_event"):
                    lead, meta = create_lead_record(
                        db,
                        ctx,
                        name="Anna",
                        phone="+79990001122",
                        inn="471405233378",
                        event_source="public.leads",
                    )

    mock_enrich.assert_called_once()
    assert meta["enrichment"]["enriched"] is True
    assert lead.name == "Anna"


def test_lookup_company_by_inn_tool():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    db = MagicMock()
    tool = LookupCompanyByInnTool()

    with patch("app.operator.tools.builtin.lookup_party_by_inn", return_value=SAMPLE_LOOKUP):
        with patch("app.operator.tools.builtin.write_audit"):
            result = tool.run(db, ctx, inn="471405233378")

    assert result.ok is True
    assert result.data["inn"] == "471405233378"


def test_create_lead_tool_delegates_to_service():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    db = MagicMock()
    fake_lead = Lead(tenant_id=tenant_id, name="Anna", phone="+79990001122", source="operator")
    fake_lead.id = uuid.uuid4()
    fake_lead.inn = "471405233378"

    tool = CreateLeadTool()
    with patch(
        "app.operator.tools.builtin.create_lead_record",
        return_value=(fake_lead, {"telegram_notified": False, "enrichment": {"enriched": True}}),
    ):
        result = tool.run(db, ctx, name="Anna", phone="+79990001122", inn="471405233378")

    assert result.ok is True
    assert result.data["party_enriched"] is True
