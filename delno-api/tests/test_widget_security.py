"""Widget security — rate limit, visitor binding, cross-tenant (Commit 2)."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.public import (
    PublicWidgetMessage,
    PublicWidgetVisitorUpdate,
    public_widget_message,
    public_widget_visitor,
)
from app.models.conversation import Conversation
from app.services.channel_router import ChannelContext
from app.services.rate_limit import get_widget_rate_limiter


def _request(ip: str = "203.0.113.10") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/public/widget/session",
        "headers": [],
        "client": (ip, 44000),
        "scheme": "http",
        "server": ("test", 80),
    }
    return Request(scope)
from app.services.rate_limit import get_widget_rate_limiter
from app.services.widget_flow import validate_widget_visitor, WidgetVisitorMismatchError


def _request(ip: str = "203.0.113.10") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/public/widget/message",
        "headers": [],
        "client": (ip, 44000),
        "scheme": "https",
        "server": ("api.dlno.ru", 443),
    }
    return Request(scope)


@pytest.fixture
def channel_ctx():
    return ChannelContext(
        tenant_id=uuid.uuid4(),
        tenant_slug="delno-demo",
        channel_type="web_widget",
        principal_id="service:delno-widget-guest",
    )


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    get_widget_rate_limiter().reset()
    yield
    get_widget_rate_limiter().reset()


def test_validate_widget_visitor_accepts_first_bind():
    conv = Conversation(id=uuid.uuid4(), tenant_id=uuid.uuid4(), channel="widget", meta={})
    validate_widget_visitor(conv, "visitor-a")
    validate_widget_visitor(conv, "visitor-a")


def test_validate_widget_visitor_rejects_mismatch():
    conv = Conversation(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        channel="widget",
        meta={"visitor_id": "visitor-a"},
    )
    with pytest.raises(WidgetVisitorMismatchError):
        validate_widget_visitor(conv, "visitor-b")
    with pytest.raises(WidgetVisitorMismatchError):
        validate_widget_visitor(conv, None)


def test_widget_message_visitor_mismatch_403(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        tenant_id=channel_ctx.tenant_id,
        channel="widget",
        meta={"visitor_id": "bound-visitor"},
    )
    body = PublicWidgetMessage(
        site_key="demo_dlno",
        session_id=str(conversation_id),
        visitor_id="other-visitor",
        message="Привет",
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.enforce_widget_rate_limit"):
            with patch("app.api.v1.public.emit_event"):
                with patch("app.api.v1.public.get_conversation_for_widget", return_value=conversation):
                    with pytest.raises(HTTPException) as exc:
                        public_widget_message(body=body, request=_request(), db=db, x_tenant_slug=None)

    assert exc.value.status_code == 403
    assert exc.value.detail == "visitor_mismatch"


def test_widget_message_cross_tenant_session_creates_new(channel_ctx):
    """session_id from another tenant must not leak — new conversation for current tenant."""
    db = MagicMock()
    foreign_session = uuid.uuid4()
    new_conv = Conversation(id=uuid.uuid4(), tenant_id=channel_ctx.tenant_id, channel="widget", meta={})
    body = PublicWidgetMessage(
        site_key="demo_dlno",
        session_id=str(foreign_session),
        visitor_id="v1",
        message="Сколько стоит доставка по городу?",
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.enforce_widget_rate_limit"):
            with patch("app.api.v1.public.emit_event"):
                with patch("app.api.v1.public.get_conversation_for_widget", return_value=new_conv):
                    with patch("app.api.v1.public.merge_widget_context", return_value={}):
                        with patch(
                            "app.api.v1.public.apply_widget_visitor",
                            return_value={"meta": {}, "lead": None, "next_step": "ask_name"},
                        ):
                            with patch(
                                "app.api.v1.public.run_operator_turn",
                                return_value={
                                    "conversation_id": str(new_conv.id),
                                    "reply": "Ответ",
                                    "sources": [],
                                },
                            ):
                                result = public_widget_message(
                                    body=body, request=_request(), db=db, x_tenant_slug=None
                                )

    assert result["message"] == "Ответ"
    assert result["conversation_id"] == str(new_conv.id)


def test_widget_rate_limit_returns_429(channel_ctx):
    db = MagicMock()
    body = PublicWidgetMessage(site_key="demo_dlno", visitor_id="v1", message="test")

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        limiter = get_widget_rate_limiter()
        with patch("app.services.widget_security.check_widget_rate_limit") as mock_rl:
            from app.services.rate_limit import RateLimitResult

            mock_rl.return_value = RateLimitResult(allowed=False, retry_after_sec=42.0)
            with pytest.raises(HTTPException) as exc:
                public_widget_message(body=body, request=_request(), db=db, x_tenant_slug=None)

    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "42"


def test_widget_visitor_endpoint_rejects_mismatch(channel_ctx):
    db = MagicMock()
    conversation_id = uuid.uuid4()
    conversation = Conversation(
        id=conversation_id,
        tenant_id=channel_ctx.tenant_id,
        channel="widget",
        meta={"visitor_id": "bound"},
    )
    body = PublicWidgetVisitorUpdate(
        site_key="demo_dlno",
        session_id=str(conversation_id),
        visitor_id="wrong",
        name="Test",
    )

    with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
        with patch("app.api.v1.public.enforce_widget_rate_limit"):
            with patch("app.api.v1.public.get_conversation_for_widget", return_value=conversation):
                with pytest.raises(HTTPException) as exc:
                    public_widget_visitor(body=body, request=_request(), db=db, x_tenant_slug=None)

    assert exc.value.status_code == 403


def test_rate_limiter_blocks_after_limit():
    limiter = get_widget_rate_limiter()
    limiter.reset()
    for _ in range(3):
        assert limiter.check("k", limit=3, window_sec=60).allowed
    blocked = limiter.check("k", limit=3, window_sec=60)
    assert not blocked.allowed
    assert blocked.retry_after_sec is not None
