"""Tenant leads list API (cabinet)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.api.v1.leads import list_leads
from app.core.tenant import TenantContext
from app.models.lead import Lead


def test_list_leads_returns_tenant_rows_only():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    lead = Lead(
        tenant_id=tenant_id,
        name="Anna",
        phone="+79990001122",
        source="website",
        status="new",
    )
    lead.id = uuid.uuid4()
    lead.created_at = datetime.now(timezone.utc)
    lead.inn = "471405233378"
    lead.party_json = {"flat": {"company_name": "ИП Test"}}

    filtered = MagicMock()
    filtered.order_by.return_value.limit.return_value.all.return_value = [lead]
    db.query.return_value.filter.return_value = filtered

    result = list_leads(limit=10, db=db, ctx=ctx)

    assert len(result["items"]) == 1
    assert result["items"][0]["name"] == "Anna"
    assert result["items"][0]["party_enriched"] is True
    db.query.return_value.filter.assert_called_once()
