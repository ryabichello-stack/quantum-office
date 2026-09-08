"""Realtime widget SDP exchange."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.public import public_widget_voice_realtime
from app.services.channel_router import ChannelContext
from app.services.rate_limit import get_widget_rate_limiter
from starlette.requests import Request


def _request(body: bytes = b"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\n") -> Request:
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "path": "/v1/public/widget/voice/realtime",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("test", 80),
    }
    req = Request(scope)

    async def read_body():
        return body

    req.body = read_body  # type: ignore[method-assign]
    return req


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    get_widget_rate_limiter().reset()
    yield
    get_widget_rate_limiter().reset()


@pytest.fixture
def channel_ctx():
    return ChannelContext(
        tenant_id=uuid.uuid4(),
        tenant_slug="delno-demo",
        channel_type="web_widget",
        principal_id="service:delno-widget-guest",
    )


def test_public_widget_voice_realtime_returns_sdp(channel_ctx):
    db = MagicMock()
    offer = b"v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\n"
    answer = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n"
    request = _request(offer)

    async def run():
        with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
            with patch(
                "app.api.v1.public.exchange_widget_realtime_sdp",
                return_value=(answer, None),
            ):
                return await public_widget_voice_realtime(
                    request=request,
                    site_key="demo_dlno",
                    session_id=None,
                    visitor_id="visitor-1",
                    db=db,
                    x_tenant_slug=None,
                )

    response = asyncio.run(run())
    assert response.body.decode("utf-8") == answer
    assert response.media_type == "application/sdp"


def test_public_widget_voice_realtime_missing_sdp(channel_ctx):
    db = MagicMock()
    request = _request(b"")

    async def run():
        with patch("app.api.v1.public._resolve_widget_context", return_value=channel_ctx):
            with pytest.raises(HTTPException) as exc:
                await public_widget_voice_realtime(
                    request=request,
                    site_key="demo_dlno",
                    session_id=None,
                    visitor_id=None,
                    db=db,
                    x_tenant_slug=None,
                )
            return exc.value.status_code

    assert asyncio.run(run()) == 400
