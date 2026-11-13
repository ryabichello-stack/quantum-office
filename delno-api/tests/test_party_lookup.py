"""E1.12 — DaData party lookup adapter, cache, tenant endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.adapters.party_lookup import (
    PartyLookupAdapter,
    extract_party_fields,
    normalize_inn,
)
from app.api.v1.tenant import tenant_party_lookup
from app.core.tenant import TenantContext
from app.models.party_cache import PartyCache
from app.services.party_enrichment import lookup_party_by_inn, upsert_party_cache

SAMPLE_SUGGESTION = {
    "value": "ИП Рябов Денис Вадимович",
    "data": {
        "inn": "471405233378",
        "ogrn": "319784700141500",
        "type": "INDIVIDUAL",
        "okved": "62.02",
        "state": {"status": "ACTIVE"},
        "name": {
            "short_with_opf": "ИП Рябов Денис Вадимович",
            "full_with_opf": "Индивидуальный предприниматель Рябов Денис Вадимович",
        },
        "fio": {"surname": "Рябов", "name": "Денис", "patronymic": "Вадимович"},
        "address": {"unrestricted_value": "190000, г. Санкт-Петербург"},
    },
}


def test_normalize_inn():
    assert normalize_inn("471405233378") == "471405233378"
    assert normalize_inn("4714 0523 3378") == "471405233378"
    assert normalize_inn("123") is None
    assert normalize_inn(None) is None


def test_extract_party_fields():
    flat = extract_party_fields(SAMPLE_SUGGESTION)
    assert flat["inn"] == "471405233378"
    assert flat["ogrn"] == "319784700141500"
    assert flat["company_name"] == "ИП Рябов Денис Вадимович"
    assert flat["director_name"] == "Рябов Денис Вадимович"
    assert flat["address"] == "190000, г. Санкт-Петербург"
    assert flat["status"] == "ACTIVE"
    assert flat["party_type"] == "INDIVIDUAL"


def test_lookup_invalid_inn_emits_failed_event():
    tenant_id = uuid.uuid4()
    db = MagicMock()

    with patch("app.services.party_enrichment.emit_event") as mock_emit:
        result = lookup_party_by_inn(db, "bad", tenant_id=tenant_id)

    assert result["ok"] is False
    assert result["error"] == "invalid_inn"
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "party.lookup_failed"


def test_lookup_cache_hit():
    tenant_id = uuid.uuid4()
    db = MagicMock()
    cached = PartyCache(
        inn="471405233378",
        ogrn="319784700141500",
        company_name="ИП Рябов Денис Вадимович",
        director_name="Рябов Денис Вадимович",
        address="190000, г. Санкт-Петербург",
        okved="62.02",
        status="ACTIVE",
        party_type="INDIVIDUAL",
        raw_json=SAMPLE_SUGGESTION,
        fetched_at=datetime.now(timezone.utc),
    )
    db.get.return_value = cached

    with patch("app.services.party_enrichment.emit_event") as mock_emit:
        result = lookup_party_by_inn(db, "471405233378", tenant_id=tenant_id)

    assert result["ok"] is True
    assert result["cached"] is True
    assert result["party"]["inn"] == "471405233378"
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "party.lookup"
    assert mock_emit.call_args.kwargs["payload"]["cached"] is True


def test_lookup_api_miss_then_cache_write():
    tenant_id = uuid.uuid4()
    db = MagicMock()
    db.get.return_value = None

    stored: dict[str, PartyCache] = {}

    def capture_add(row: PartyCache) -> None:
        stored[row.inn] = row

    db.add.side_effect = capture_add
    db.flush = MagicMock()

    adapter = MagicMock(spec=PartyLookupAdapter)
    adapter.configured.return_value = True
    adapter.find_by_inn.return_value = [SAMPLE_SUGGESTION]

    with patch("app.services.party_enrichment.emit_event") as mock_emit:
        result = lookup_party_by_inn(
            db,
            "471405233378",
            tenant_id=tenant_id,
            adapter=adapter,
        )

    assert result["ok"] is True
    assert result["cached"] is False
    assert result["flat"]["company_name"] == "ИП Рябов Денис Вадимович"
    adapter.find_by_inn.assert_called_once_with("471405233378")
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["payload"]["cached"] is False


def test_lookup_not_configured():
    db = MagicMock()
    db.get.return_value = None
    adapter = MagicMock(spec=PartyLookupAdapter)
    adapter.configured.return_value = False

    result = lookup_party_by_inn(db, "471405233378", adapter=adapter)
    assert result["ok"] is False
    assert result["error"] == "dadata_not_configured"


def test_upsert_party_cache_updates_existing():
    db = MagicMock()
    existing = PartyCache(inn="471405233378", raw_json={})
    db.get.return_value = existing

    row = upsert_party_cache(db, SAMPLE_SUGGESTION)
    assert row.inn == "471405233378"
    assert row.company_name == "ИП Рябов Денис Вадимович"
    db.add.assert_not_called()


def test_tenant_party_lookup_endpoint_invalid_inn():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role="tenant_owner")
    db = MagicMock()

    with patch("app.api.v1.tenant.lookup_party_by_inn", return_value={"ok": False, "error": "invalid_inn"}):
        with pytest.raises(HTTPException) as exc:
            tenant_party_lookup(inn="xxx", force=False, db=db, ctx=ctx)
    assert exc.value.status_code == 400


def test_tenant_party_lookup_endpoint_commits():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="demo", role="tenant_owner")
    db = MagicMock()
    payload = {"ok": True, "cached": True, "inn": "471405233378", "party": {}, "flat": {}}

    with patch("app.api.v1.tenant.lookup_party_by_inn", return_value=payload) as mock_lookup:
        result = tenant_party_lookup(inn="471405233378", force=False, db=db, ctx=ctx)

    assert result["ok"] is True
    mock_lookup.assert_called_once()
    assert mock_lookup.call_args.kwargs["tenant_id"] == ctx.tenant_id
    db.commit.assert_called_once()
