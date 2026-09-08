"""Unit tests for realtime_widget service."""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.tools.registry import ToolResult
from app.services.realtime_widget import (
    exchange_widget_realtime_sdp,
    load_widget_kb_context,
    safety_identifier,
)


def test_safety_identifier_hashes_visitor():
    assert safety_identifier("visitor-1") != "visitor-1"
    assert len(safety_identifier("visitor-1") or "") == 32


def test_load_widget_kb_context_from_tool():
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="public")
    with patch("app.services.realtime_widget.registry.run") as mock_run:
        mock_run.return_value = ToolResult(ok=True, data={"text": "Тариф 2990"})
        text = load_widget_kb_context(db, ctx)
    assert "2990" in text


def test_exchange_widget_realtime_sdp_no_api_key():
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="public")
    with patch("app.services.realtime_widget.get_openai_runtime", return_value={"api_key": "", "realtime_model": "gpt-realtime-2.1-mini", "realtime_voice": "cedar", "model": "gpt-4.1-mini"}):
        answer, error = exchange_widget_realtime_sdp(db, ctx, sdp_offer="v=0", visitor_id="v1")
    assert answer is None
    assert error == "VOICE_NOT_CONFIGURED"


def test_exchange_widget_realtime_sdp_sends_sdp_as_form_field():
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="public")
    offer = "v=0\r\no=- 0 0 IN IP4 127.0.0.1\r\n"
    answer_sdp = "v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\n"

    class FakeResponse:
        status_code = 201
        text = answer_sdp

    with patch("app.services.realtime_widget.get_openai_runtime", return_value={"api_key": "sk-test", "realtime_model": "gpt-realtime-2.1-mini", "realtime_voice": "cedar", "model": "gpt-4.1-mini"}):
        with patch("app.services.realtime_widget.load_widget_kb_context", return_value=""):
            with patch("app.services.realtime_widget.build_widget_realtime_instructions", return_value="hi"):
                with patch("app.services.realtime_widget.httpx.post", return_value=FakeResponse()) as mock_post:
                    answer, error = exchange_widget_realtime_sdp(db, ctx, sdp_offer=offer, visitor_id="v1")

    assert error is None
    assert answer is not None and answer.startswith("v=0")
    files = mock_post.call_args.kwargs["files"]
    assert files["sdp"][0] is None
    assert files["sdp"][1] == offer
    assert files["session"][0] is None
    assert json.loads(files["session"][1])["type"] == "realtime"
