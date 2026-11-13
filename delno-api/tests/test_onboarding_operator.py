"""O1 — onboarding channel system prompt."""

from unittest.mock import MagicMock, patch

from app.core.tenant import TenantContext
from app.operator.agent import _generate_reply, _system_prompt


def test_onboarding_system_prompt_mentions_conversation_not_kb_form():
    ctx = TenantContext(tenant_id=MagicMock(), tenant_slug="salon", role="tenant_owner")
    prompt = _system_prompt(ctx, "", onboarding=True)
    assert "onboarding" in prompt.lower() or "разговор" in prompt.lower()
    assert "базу знаний" in prompt.lower() or "KB" in prompt
    assert "черновик" in prompt.lower() or "draft" in prompt.lower()


def test_generate_reply_onboarding_channel_uses_onboarding_prompt():
    ctx = TenantContext(tenant_id=MagicMock(), tenant_slug="salon", role="tenant_owner")
    db = MagicMock()

    with patch("app.operator.agent.registry") as mock_registry:
        mock_registry.run.return_value = MagicMock(ok=False)
        with patch("app.operator.agent.get_model_provider") as mock_provider:
            mock_provider.return_value.chat_completion.return_value = {
                "ok": True,
                "provider": "stub",
                "data": {"choices": [{"message": {"content": "Расскажите о вашем бизнесе."}}]},
            }
            _generate_reply(db, ctx, "Привет", channel="onboarding")

    call_args = mock_provider.return_value.chat_completion.call_args
    system_content = call_args.kwargs["messages"][0]["content"]
    assert "onboarding" in system_content.lower() or "разговор" in system_content.lower()
