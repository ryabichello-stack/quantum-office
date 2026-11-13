"""DIY turns must land in conversation history."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.agent import persist_operator_exchange


def test_persist_operator_exchange_writes_two_messages():
    db = MagicMock()
    conv = MagicMock()
    conv.id = uuid.uuid4()
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="t", role="tenant_owner")

    with patch("app.operator.agent._get_or_create_conversation", return_value=conv), patch(
        "app.operator.agent.write_audit"
    ):
        cid = persist_operator_exchange(
            db,
            ctx,
            message="подключи телеграм",
            reply="Есть два способа",
            channel="hermes",
            assistant_meta={"engine": "diy_channel_chooser"},
        )

    assert cid == str(conv.id)
    assert db.add.call_count >= 2
    bodies = [c.args[0].body for c in db.add.call_args_list if hasattr(c.args[0], "body")]
    assert "подключи телеграм" in bodies
    assert "Есть два способа" in bodies
    db.commit.assert_called_once()
