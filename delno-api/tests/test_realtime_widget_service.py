"""Unit tests for realtime_widget service."""

from __future__ import annotations

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
    with patch("app.services.realtime_widget.get_settings") as mock_settings:
        mock_settings.return_value.openai_api_key = ""
        answer, error = exchange_widget_realtime_sdp(db, ctx, sdp_offer="v=0", visitor_id="v1")
    assert answer is None
    assert error == "VOICE_NOT_CONFIGURED"
