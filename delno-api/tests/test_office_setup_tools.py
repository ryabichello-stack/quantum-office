"""Agent-callable telephony / cloud / credential tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.tools.office_setup import (
    CredentialsOpenFormTool,
    TelephonyToolsSetTool,
)
import uuid


def test_credentials_open_form_returns_pending_form():
    tool = CredentialsOpenFormTool()
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="t", role="tenant_owner")
    out = tool.run(db, ctx, kind="files_yadisk")
    assert out.ok
    form = (out.data or {}).get("pending_credential_form")
    assert form and form.get("kind") == "files_yadisk"


def test_telephony_tools_set_calls_service():
    tool = TelephonyToolsSetTool()
    db = MagicMock()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="t", role="tenant_owner")
    with patch("app.operator.tools.office_setup.telephony_script.set_telephony_tools") as set_tools:
        set_tools.return_value = {"ok": True, "message_ru": "Tools для линии обновлены: x", "tools": ["x"]}
        out = tool.run(
            db,
            ctx,
            tools=["check_calendar", "create_conference", "send_email"],
        )
    assert out.ok
    set_tools.assert_called_once()
