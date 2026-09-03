"""Widget session + visitor lead capture."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.public import (
    PublicWidgetMessage,
    PublicWidgetSession,
    PublicWidgetVisitorUpdate,
    public_widget_message,
    public_widget_session,
    public_widget_visitor,
)
from app.models.conversation import Conversation
from app.services.channel_router import ChannelContext


@pytest.fixture
def channel_ctx():
    tenant_id = uuid.uuid4()
    return ChannelContext(
        tenant_id=tenant_id,
        tenant_slug="delno-demo",
        channel_type="web_widget",
        principal_id="service:delno-widget-guest",
    )


def test_public_widget_session_creates_conversation(channel_ctx):
    db = MagicMock()
    body = PublicWidgetSession(site_key="demo_dlno", visitor_id="v1", page_url="https://dlno.ru/")

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.emit_event"):
            with patch("app.api.v1.public.tenant_public_profile", return_value={"name": "DELNO", "assistant_name": "DELNO"}):
                result = public_widget_session(body=body, db=db, x_tenant_slug=None)

    assert result["session_id"]
    assert result["widget"]["collect_name"] is True
    assert result["next_step"] == "ask_name"
    db.commit.assert_called_once()


def test_public_widget_visitor_creates_lead(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    conversation = Conversation(id=conversation_id, tenant_id=channel_ctx.tenant_id, channel="widget", meta={})
    fake_lead_id = uuid.uuid4()

    body = PublicWidgetVisitorUpdate(
        site_key="demo_dlno",
        session_id=str(conversation_id),
        name="Алексей",
        phone="+7 999 123-45-67",
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.get_conversation_for_widget", return_value=conversation):
            with patch("app.api.v1.public.merge_widget_context", return_value={"visitor_name": "Алексей"}):
                with patch(
                    "app.api.v1.public.apply_widget_visitor",
                    return_value={
                        "meta": {"visitor_name": "Алексей", "lead_id": str(fake_lead_id)},
                        "lead": {"id": str(fake_lead_id), "name": "Алексей", "phone": "+79991234567"},
                        "next_step": None,
                    },
                ):
                    result = public_widget_visitor(body=body, db=db, x_tenant_slug=None)

    assert result["ok"] is True
    assert result["lead"]["name"] == "Алексей"
    assert result["next_step"] is None
    db.commit.assert_called_once()


def test_public_widget_message_returns_ask_phone(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        tenant_id=channel_ctx.tenant_id,
        channel="widget",
        meta={"visitor_name": "Алексей"},
    )
    body = PublicWidgetMessage(
        site_key="demo_dlno",
        session_id=str(conversation_id),
        message="Сколько стоит доставка?",
        visitor={"name": "Алексей"},
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.emit_event"):
            with patch("app.api.v1.public.get_conversation_for_widget", return_value=conversation):
                with patch("app.api.v1.public.merge_widget_context", return_value={"visitor_name": "Алексей"}):
                    with patch(
                        "app.api.v1.public.apply_widget_visitor",
                        return_value={"meta": {"visitor_name": "Алексей"}, "lead": None, "next_step": "ask_phone"},
                    ):
                        with patch(
                            "app.api.v1.public.run_operator_turn",
                            return_value={
                                "conversation_id": str(conversation_id),
                                "reply": "Доставка стоит 500 ₽",
                                "sources": [],
                                "tool_calls": [],
                            },
                        ):
                            result = public_widget_message(body=body, db=db, x_tenant_slug=None)

    assert "Доставка" in result["message"]
    assert result["next_step"] == "ask_phone"


def test_public_widget_unknown_site_key():
    db = MagicMock()
    body = PublicWidgetMessage(site_key="unknown_key", message="Привет")

    with patch("app.api.v1.public._resolve_widget_context", return_value=None):
        with pytest.raises(HTTPException) as exc:
            public_widget_message(body=body, db=db, x_tenant_slug=None)

    assert exc.value.status_code == 404
