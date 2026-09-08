"""E0.15 — operational events: lead.created, auth.failed, operator.error, knowledge.search_failed."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.auth import login
from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.models.platform_event import PlatformEvent
from app.operator.agent import run_operator_turn
from app.operator.tools.builtin import GetKnowledgeTool
from app.schemas.auth import LoginRequest
from app.services.events import emit_event, list_events_for_tenant


def test_emit_event_payload_includes_source_and_recorded_at():
    db = MagicMock()
    tenant_id = uuid.uuid4()

    event = emit_event(
        db,
        tenant_id=tenant_id,
        event_type="lead.created",
        source="test.harness",
        payload={"lead_id": "abc"},
    )

    assert event.tenant_id == tenant_id
    assert event.event_type == "lead.created"
    assert event.payload["source"] == "test.harness"
    assert event.payload["lead_id"] == "abc"
    assert "recorded_at" in event.payload
    db.add.assert_called_once()
    db.flush.assert_called_once()


def test_list_events_for_tenant_filters_by_tenant_id():
    tenant_a = uuid.uuid4()
    db = MagicMock()

    event_a = PlatformEvent(
        tenant_id=tenant_a,
        event_type="lead.created",
        category="operational",
        payload={"source": "test"},
    )
    filtered = MagicMock()
    filtered.order_by.return_value.limit.return_value.all.return_value = [event_a]
    db.query.return_value.filter.return_value.filter.return_value = filtered

    rows = list_events_for_tenant(db, tenant_a, event_type="lead.created")
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant_a


def test_auth_failed_emits_event_and_commits():
    db = MagicMock()
    db.query.return_value.filter.return_value.one_or_none.return_value = None
    body = LoginRequest(email="nobody@delno.one", password="wrong12")

    with patch("app.api.v1.auth.emit_event") as mock_emit:
        with pytest.raises(HTTPException) as exc:
            login(body, db=db)

    assert exc.value.status_code == 401
    mock_emit.assert_called_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["event_type"] == "auth.failed"
    assert kwargs["source"] == "auth.login"
    assert kwargs["payload"]["reason"] == "invalid_credentials"
    assert kwargs["payload"]["email"] == "nobody@delno.one"
    db.commit.assert_called_once()


def test_knowledge_search_failed_emits_event():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    class _FailingAdapter:
        def search(self, *args, **kwargs):
            return {"ok": False, "message": "Knowledge service HTTP 503"}

    tool = GetKnowledgeTool(_FailingAdapter())

    with patch("app.operator.tools.builtin.emit_event") as mock_emit:
        with patch("app.operator.tools.builtin.write_audit"):
            result = tool.run(db, ctx, query="тарифы")

    assert result.ok is False
    mock_emit.assert_called_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["event_type"] == "knowledge.search_failed"
    assert kwargs["source"] == "operator.get_knowledge"
    assert kwargs["payload"]["query"] == "тарифы"
    assert "503" in kwargs["payload"]["message"]


def test_operator_error_emits_on_exception():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()
    db.commit = MagicMock()

    with patch("app.operator.agent._get_or_create_conversation", side_effect=RuntimeError("db down")):
        with patch("app.operator.agent.emit_event") as mock_emit:
            with pytest.raises(RuntimeError, match="db down"):
                run_operator_turn(db, ctx, message="Привет")

    mock_emit.assert_called_once()
    kwargs = mock_emit.call_args.kwargs
    assert kwargs["tenant_id"] == tenant_id
    assert kwargs["event_type"] == "operator.error"
    assert kwargs["source"] == "operator.chat"
    assert kwargs["payload"]["stage"] == "run_operator_turn"
    assert "db down" in kwargs["payload"]["error"]
    db.commit.assert_called_once()


def test_create_lead_tool_emits_lead_created():
    tenant_id = uuid.uuid4()
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()
    fake_lead = Lead(tenant_id=tenant_id, name="Anna", phone="+79990001122", source="operator")
    fake_lead.id = uuid.uuid4()

    from app.operator.tools.builtin import CreateLeadTool

    tool = CreateLeadTool()
    with patch(
        "app.operator.tools.builtin.create_lead_record",
        return_value=(fake_lead, {"telegram_notified": False, "enrichment": {"enriched": False}}),
    ) as mock_create:
        result = tool.run(db, ctx, name="Anna", phone="+79990001122")

    assert result.ok is True
    mock_create.assert_called_once()
    assert mock_create.call_args.kwargs["event_source"] == "operator.create_lead"
