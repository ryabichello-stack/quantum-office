import uuid
from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.agent import _generate_reply, run_operator_turn
from app.operator.tools.registry import ToolResult


def test_generate_reply_uses_kb_text_and_stub_llm():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    kb_data = {
        "ok": True,
        "text": "DELNO — ИИ-сотрудник. Тариф Диалоги от 2990 руб.",
        "matches": [{"snippet": "DELNO — ИИ-сотрудник. Тариф Диалоги от 2990 руб."}],
    }

    with patch("app.operator.agent.registry") as mock_registry:
        mock_registry.run.return_value = ToolResult(ok=True, data=kb_data)
        with patch("app.operator.agent.get_model_provider") as mock_provider:
            mock_provider.return_value.chat_completion.return_value = {
                "ok": True,
                "provider": "stub",
                "data": {"choices": [{"message": {"content": "Тариф Диалоги — 2 990 ₽/мес."}}]},
            }
            reply, tool_calls, sources = _generate_reply(db, ctx, "Сколько стоит DELNO?")

    assert "2 990" in reply or "2990" in reply
    assert any(t.get("tool") == "get_knowledge" for t in tool_calls)
    assert isinstance(sources, list)
    mock_registry.run.assert_called_once_with(db, ctx, "get_knowledge", query="Сколько стоит DELNO?")


def test_generate_reply_fallback_without_llm():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    with patch("app.operator.agent.registry") as mock_registry:
        mock_registry.run.return_value = ToolResult(
            ok=True,
            data={"text": "Комиссия за СБП составляет 1%."},
        )
        with patch("app.operator.agent.get_model_provider") as mock_provider:
            mock_provider.return_value.chat_completion.return_value = {"ok": False, "error": "no_key"}
            reply, tool_calls, sources = _generate_reply(db, ctx, "комиссия")

    assert "1%" in reply
    assert tool_calls[0]["tool"] == "get_knowledge"
    assert sources == []


def test_generate_reply_ignores_stub_echo():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()

    with patch("app.operator.agent.registry") as mock_registry:
        mock_registry.run.return_value = ToolResult(
            ok=True,
            data={"text": "Тариф Диалоги — 2 990 ₽/мес."},
        )
        with patch("app.operator.agent.get_model_provider") as mock_provider:
            mock_provider.return_value.chat_completion.return_value = {
                "ok": True,
                "provider": "stub",
                "data": {"choices": [{"message": {"content": "[stub] Сколько стоит?"}}]},
            }
            reply, tool_calls, _sources = _generate_reply(db, ctx, "Сколько стоит?")

    assert "2 990" in reply
    assert any(t.get("tool") == "llm" and t.get("ok") is False for t in tool_calls)


def test_run_operator_turn_commits_messages():
    ctx = TenantContext(tenant_id=uuid.uuid4(), tenant_slug="delno-demo", role="tenant_owner")
    db = MagicMock()
    conversation = MagicMock()
    conversation.id = uuid.uuid4()
    db.flush = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()

    with patch("app.operator.agent._get_or_create_conversation", return_value=conversation):
        with patch("app.operator.agent._generate_reply", return_value=("Ответ", [{"tool": "get_knowledge", "ok": True}], [])):
            with patch("app.operator.agent.write_audit"):
                result = run_operator_turn(db, ctx, message="Привет")

    assert result["reply"] == "Ответ"
    assert db.commit.called
