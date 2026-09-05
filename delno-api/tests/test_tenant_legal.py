"""E1.15 — tenant legal profile in settings.legal from INN."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.tenant import TenantLegalUpdate, get_tenant_legal, update_tenant_legal
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.party_enrichment import build_tenant_legal_profile, enrich_tenant_legal_from_inn

SAMPLE_LOOKUP = {
    "ok": True,
    "cached": True,
    "inn": "471405233378",
    "flat": {
        "inn": "471405233378",
        "ogrn": "319784700141500",
        "company_name": "ИП Рябов Денис Вадимович",
        "address": "190000, г. Санкт-Петербург",
        "okved": "62.02",
        "party_type": "INDIVIDUAL",
    },
}


def test_build_tenant_legal_profile_includes_ogrnip_for_ip():
    legal = build_tenant_legal_profile(SAMPLE_LOOKUP["flat"])
    assert legal["inn"] == "471405233378"
    assert legal["ogrnip"] == "319784700141500"
    assert legal["company_name"] == "ИП Рябов Денис Вадимович"
    assert "enriched_at" in legal


def test_enrich_tenant_legal_sets_settings():
    tenant_id = uuid.uuid4()
    tenant = Tenant(slug="demo", name="Demo", settings={"locale": "ru"})
    tenant.id = tenant_id
    db = MagicMock()

    with patch("app.services.party_enrichment.lookup_party_by_inn", return_value=SAMPLE_LOOKUP):
        with patch("app.services.party_enrichment.emit_event") as mock_emit:
            result = enrich_tenant_legal_from_inn(db, tenant, "471405233378", tenant_id=tenant_id)

    assert result["enriched"] is True
    assert tenant.settings["legal"]["inn"] == "471405233378"
    assert tenant.settings["locale"] == "ru"
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["payload"]["target"] == "tenant"


def test_enrich_tenant_legal_invalid_inn():
    tenant = Tenant(slug="demo", name="Demo", settings={})
    db = MagicMock()
    result = enrich_tenant_legal_from_inn(db, tenant, "bad", tenant_id=uuid.uuid4())
    assert result["enriched"] is False


def test_get_tenant_legal_endpoint():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={"legal": {"inn": "471405233378"}})
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    result = get_tenant_legal(db=db, ctx=ctx)
    assert result["ok"] is True
    assert result["legal"]["inn"] == "471405233378"


def test_update_tenant_legal_endpoint():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="demo", role="tenant_owner")
    tenant = Tenant(slug="demo", name="Demo", settings={})
    tenant.id = tenant_id
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    legal = {"inn": "471405233378", "company_name": "ИП Рябов Денис Вадимович"}

    with patch(
        "app.api.v1.tenant.enrich_tenant_legal_from_inn",
        return_value={"enriched": True, "legal": legal},
    ):
        with patch("app.api.v1.tenant.write_audit"):
            result = update_tenant_legal(
                TenantLegalUpdate(inn="471405233378"),
                db=db,
                ctx=ctx,
            )

    assert result["party_enriched"] is True
    assert result["legal"]["inn"] == "471405233378"
    db.commit.assert_called_once()


def test_update_tenant_legal_forbidden_for_member():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role="tenant_member")
    db = MagicMock()

    with pytest.raises(HTTPException) as exc:
        update_tenant_legal(TenantLegalUpdate(inn="471405233378"), db=db, ctx=ctx)
    assert exc.value.status_code == 403
