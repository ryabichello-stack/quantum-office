import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.agent import _generate_reply, _try_cabinet_setup
from app.operator.setup_intent import parse_setup_intent


def test_parse_setup_intent_kb():
    intent = parse_setup_intent("Добавь в базу знаний: Часы работы — суббота 10:00–16:00")
    assert intent is not None
    assert intent["tool"] == "upload_knowledge_snippet"
    assert intent["params"]["title"] == "Часы работы"


def test_parse_setup_intent_flag():
    intent = parse_setup_intent("Включи голос на сайте")
    assert intent is not None
    assert intent["tool"] == "set_feature_flag"
    assert intent["params"]["flag_key"] == "web_voice"
    assert intent["params"]["enabled"] is True


def test_parse_setup_intent_summary():
    intent = parse_setup_intent("Покажи текущие настройки")
    assert intent is not None
    assert intent["tool"] == "get_tenant_summary"


def test_cabinet_setup_pending_confirmation():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    with patch("app.operator.agent.registry") as mock_registry:
        tool = MagicMock()
        tool.critical_write = True
        mock_registry.get.return_value = tool

        reply, tool_calls, _sources, pending = _try_cabinet_setup(
            db,
            ctx,
            "Добавь в базу знаний: Прайс — консультация 3000 руб.",
        )

    assert pending is not None
    assert pending["tool_name"] == "upload_knowledge_snippet"
    assert "Готов выполнить" in reply
    assert tool_calls[0]["tool"] == "upload_knowledge_snippet"


def test_generate_reply_cabinet_skips_llm_on_setup():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    with patch("app.operator.agent._try_cabinet_setup") as mock_setup:
        mock_setup.return_value = (
            "OK",
            [{"tool": "set_feature_flag"}],
            [],
            {"tool_name": "set_feature_flag"},
        )
        reply, _tool_calls, _sources, pending = _generate_reply(
            db, ctx, "Включи telegram", channel="cabinet"
        )

    assert reply == "OK"
    assert pending is not None
    mock_setup.assert_called_once()
