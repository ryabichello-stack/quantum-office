from app.services.openai_http import openai_base_url, openai_proxy_url, openai_url


def test_openai_url_join(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1/")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert openai_base_url() == "https://api.openai.com/v1"
    assert openai_url("chat/completions") == "https://api.openai.com/v1/chat/completions"
    assert openai_url("/audio/speech") == "https://api.openai.com/v1/audio/speech"
    get_settings.cache_clear()


def test_openai_proxy_prefers_explicit(monkeypatch):
    monkeypatch.setenv("OPENAI_HTTP_PROXY", "socks5://127.0.0.1:1080")
    monkeypatch.setenv("HTTPS_PROXY", "http://ignored:9")
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert openai_proxy_url() == "socks5://127.0.0.1:1080"
    get_settings.cache_clear()
