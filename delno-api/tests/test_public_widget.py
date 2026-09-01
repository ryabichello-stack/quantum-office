"""Public widget message gateway."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.public import PublicWidgetMessage, public_widget_message
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


def test_public_widget_message_calls_operator(channel_ctx):
    db = MagicMock()
    body = PublicWidgetMessage(
        site_key="demo_dlno",
        message="Сколько стоит доставка по городу?",
        visitor_id="visitor-1",
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.emit_event"):
            with patch(
                "app.api.v1.public.run_operator_turn",
                return_value={
                    "conversation_id": str(uuid.uuid4()),
                    "reply": "Доставка стоит 500 ₽",
                    "sources": [{"title": "Доставка"}],
                    "tool_calls": [],
                },
            ) as mock_turn:
                result = public_widget_message(body=body, db=db, x_tenant_slug=None)

    assert "Доставка" in result["message"]
    assert result["next_step"] == "ask_name"
    mock_turn.assert_called_once()


def test_public_widget_unknown_site_key():
    db = MagicMock()
    body = PublicWidgetMessage(site_key="unknown_key", message="Привет")

    with patch("app.api.v1.public._resolve_widget_context", return_value=None):
        with pytest.raises(HTTPException) as exc:
            public_widget_message(body=body, db=db, x_tenant_slug=None)

    assert exc.value.status_code == 404
