from app.services.model_provider import StubProvider, get_model_provider


def test_stub_provider():
    p = StubProvider()
    out = p.chat_completion(messages=[{"role": "user", "content": "Привет"}])
    assert out["ok"] is True
    assert "stub" in out["data"]["choices"][0]["message"]["content"]


def test_get_model_provider_without_key():
    from unittest.mock import patch

    with patch("app.services.model_provider.get_settings") as mock:
        mock.return_value.model_provider = "openai"
        mock.return_value.openai_api_key = None
        provider = get_model_provider()
        assert provider.name == "stub"
