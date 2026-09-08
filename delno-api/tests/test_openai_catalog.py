"""OpenAI catalog fetch for admin dropdowns."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.services.openai_catalog import (
    REALTIME_MODEL_FALLBACK,
    fetch_openai_options,
    verify_openai_api_key,
)


def test_fetch_openai_options_fallback_without_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    from app.core.config import get_settings

    get_settings.cache_clear()
    with patch("app.services.openai_catalog.read_env_values", return_value={}):
        result = fetch_openai_options(force_refresh=True)
    assert result["source"] == "fallback"
    assert result["fetch_error"] == "openai_key_missing"
    assert result["realtime_models"] == list(REALTIME_MODEL_FALLBACK) or result["realtime_models"]


def test_fetch_openai_options_from_api():
    from app.core.config import get_settings

    get_settings.cache_clear()
    fake_models = {
        "data": [
            {"id": "gpt-4.1-mini"},
            {"id": "gpt-realtime-2.1"},
            {"id": "gpt-realtime-2.1-mini"},
            {"id": "text-embedding-3-small"},
        ]
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return fake_models

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResponse()

    with patch("app.services.openai_catalog.read_env_values", return_value={"OPENAI_API_KEY": "sk-test"}):
        with patch("app.services.openai_catalog.httpx.Client", FakeClient):
            result = fetch_openai_options(force_refresh=True)

    assert result["source"] == "openai"
    assert "gpt-realtime-2.1" in result["realtime_models"]
    assert "gpt-4.1-mini" in result["chat_models"]
    assert "cedar" in result["realtime_voices"]


def test_verify_openai_api_key_ok():
    fake_models = {
        "data": [
            {"id": "gpt-4.1-mini"},
            {"id": "gpt-realtime-2.1"},
        ]
    }

    class FakeResponse:
        status_code = 200

        def json(self):
            return fake_models

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, headers=None):
            return FakeResponse()

    with patch("app.services.openai_catalog.httpx.Client", FakeClient):
        result = verify_openai_api_key("sk-test-key-with-enough-length")

    assert result["ok"] is True
    assert result["realtime_models_count"] == 1
    assert result["chat_models_count"] == 1


def test_verify_openai_api_key_invalid_format():
    result = verify_openai_api_key("admin123456")
    assert result["ok"] is False
    assert result["error"] == "openai_key_invalid_format"
