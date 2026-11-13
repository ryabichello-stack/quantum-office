"""E1.14 — DaData party suggest (autocomplete)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.adapters.party_lookup import PartyLookupAdapter
from app.api.v1.public import PublicPartySuggest, public_party_suggest
from app.api.v1.tenant import tenant_party_suggest
from app.core.tenant import TenantContext
from app.services.channel_router import ChannelContext
from app.services.party_enrichment import suggest_parties_by_query

SAMPLE_SUGGESTION = {
    "value": "ИП Рябов Денис Вадимович",
    "data": {
        "inn": "471405233378",
        "type": "INDIVIDUAL",
        "name": {"short_with_opf": "ИП Рябов Денис Вадимович"},
        "address": {"unrestricted_value": "190000, г. Санкт-Петербург"},
        "state": {"status": "ACTIVE"},
    },
}


def test_suggest_parties_by_query_success():
    tenant_id = uuid.uuid4()
    db = MagicMock()
    adapter = MagicMock(spec=PartyLookupAdapter)
    adapter.configured.return_value = True
    adapter.suggest_parties.return_value = [SAMPLE_SUGGESTION]

    with patch("app.services.party_enrichment.emit_event") as mock_emit:
        result = suggest_parties_by_query(
            db,
            "рябов",
            tenant_id=tenant_id,
            adapter=adapter,
        )

    assert result["ok"] is True
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["inn"] == "471405233378"
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "party.suggest"


def test_suggest_parties_query_too_short():
    db = MagicMock()
    result = suggest_parties_by_query(db, "a")
    assert result["ok"] is False
    assert result["error"] == "query_too_short"


def test_public_party_suggest_endpoint():
    tenant_id = uuid.uuid4()
    db = MagicMock()
    channel = ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="delno-demo",
        channel_type="website",
        principal_id="service:delno-widget-guest",
    )

    with patch("app.api.v1.public.resolve_public_lead", return_value=channel):
        with patch(
            "app.api.v1.public.suggest_parties_by_query",
            return_value={"ok": True, "query": "рябов", "suggestions": []},
        ):
            result = public_party_suggest(
                PublicPartySuggest(q="рябов"),
                db=db,
                x_tenant_slug="delno-demo",
            )

    assert result["ok"] is True
    db.commit.assert_called_once()


def test_tenant_party_suggest_endpoint():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    with patch(
        "app.api.v1.tenant.suggest_parties_by_query",
        return_value={"ok": True, "query": "4714", "suggestions": []},
    ):
        result = tenant_party_suggest(q="4714", count=5, db=db, ctx=ctx)

    assert result["ok"] is True
    db.commit.assert_called_once()


def test_public_party_suggest_unknown_tenant():
    db = MagicMock()
    with patch("app.api.v1.public.resolve_public_lead", return_value=None):
        with pytest.raises(HTTPException) as exc:
            public_party_suggest(
                PublicPartySuggest(q="рябов"),
                db=db,
                x_tenant_slug="missing",
            )
    assert exc.value.status_code == 404
