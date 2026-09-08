"""O1 — onboarding draft knowledge + start flow."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.conversation import Conversation
from app.models.tenant import Tenant
from app.services.knowledge_documents import upsert_draft_knowledge, upsert_tenant_knowledge_document
from app.services.onboarding_flow import ONBOARDING_WELCOME, start_onboarding


@pytest.fixture
def tenant_and_ctx():
    tenant_id = uuid.uuid4()
    tenant = Tenant(
        id=tenant_id,
        slug="salon-demo",
        name="Salon Demo",
        public_key="pk_test",
        settings={"locale": "ru"},
    )
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="salon-demo", role="tenant_owner")
    return tenant, ctx


def test_upsert_draft_knowledge_sends_unpublished_company_payload(tenant_and_ctx):
    tenant, _ctx = tenant_and_ctx
    db = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "document_id": "doc-salon-demo-price"}

    with patch("app.services.knowledge_documents.httpx.Client") as mock_client_cls:
        client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = client
        client.post.return_value = mock_response
        with patch("app.services.knowledge_documents.get_settings") as mock_settings:
            mock_settings.return_value.knowledge_base_url = "http://knowledge:8021"
            result = upsert_draft_knowledge(
                db,
                tenant,
                title="Прайс",
                body="Маникюр 1500 руб. Педикюр 2000 руб.",
                source="onboarding.file",
            )

    assert result["ok"] is True
    _url, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["visibility"] == "company"
    assert payload["status"] == "draft"
    assert payload["index_zone"] == "private"
    assert payload["publication"] == {"status": "unpublished"}
    assert payload["source"] == "onboarding.file"


def test_upsert_tenant_knowledge_document_unchanged_without_draft_fields(tenant_and_ctx):
    tenant, _ctx = tenant_and_ctx
    db = MagicMock()
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "document_id": "doc-salon-demo-faq"}

    with patch("app.services.knowledge_documents.httpx.Client") as mock_client_cls:
        client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = client
        client.post.return_value = mock_response
        with patch("app.services.knowledge_documents.get_settings") as mock_settings:
            mock_settings.return_value.knowledge_base_url = "http://knowledge:8021"
            upsert_tenant_knowledge_document(
                db,
                tenant,
                title="FAQ",
                body="Ответы на частые вопросы клиентов компании.",
                visibility="public",
            )

    _url, kwargs = client.post.call_args
    payload = kwargs["json"]
    assert payload["visibility"] == "public"
    assert "status" not in payload
    assert "publication" not in payload


def test_start_onboarding_creates_conversation_and_event(tenant_and_ctx):
    tenant, ctx = tenant_and_ctx
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        if model is Tenant:
            q.filter.return_value.one.return_value = tenant
        elif model is Conversation:
            q.filter.return_value.one_or_none.return_value = None
        return q

    db.query.side_effect = _query

    with patch("app.services.onboarding_flow.emit_event") as mock_emit:
        result = start_onboarding(db, ctx)

    assert result["ok"] is True
    assert result["resumed"] is False
    assert result["reply"] == ONBOARDING_WELCOME
    assert result["conversation_id"]
    assert tenant.settings["onboarding"]["status"] == "in_progress"
    assert tenant.settings["onboarding"]["conversation_id"] == result["conversation_id"]
    mock_emit.assert_called_once()
    assert mock_emit.call_args.kwargs["event_type"] == "onboarding.started"
    db.commit.assert_called_once()


def test_start_onboarding_resumes_existing_conversation(tenant_and_ctx):
    tenant, ctx = tenant_and_ctx
    conversation_id = uuid.uuid4()
    tenant.settings = {
        "onboarding": {
            "status": "in_progress",
            "conversation_id": str(conversation_id),
            "started_at": "2026-09-04T09:00:00+00:00",
        }
    }
    conversation = Conversation(
        id=conversation_id,
        tenant_id=tenant.id,
        channel="onboarding",
        meta={"mode": "onboarding"},
    )
    db = MagicMock()

    def _query(model):
        q = MagicMock()
        if model is Tenant:
            q.filter.return_value.one.return_value = tenant
        elif model is Conversation:
            q.filter.return_value.one_or_none.return_value = conversation
        return q

    db.query.side_effect = _query

    result = start_onboarding(db, ctx)
    assert result["ok"] is True
    assert result["resumed"] is True
    assert result["conversation_id"] == str(conversation_id)
    db.commit.assert_not_called()
