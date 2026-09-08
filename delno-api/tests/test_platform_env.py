"""Platform env file management."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.services.platform_env import (
    ALLOWED_KEYS,
    mask_secret,
    normalize_openai_api_key,
    platform_env_path,
    read_env_values,
    update_env_values,
)


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=old-key\nOPENAI_MODEL=gpt-4.1-mini\n", encoding="utf-8")
    monkeypatch.setenv("PLATFORM_ENV_FILE", str(path))
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield path
    get_settings.cache_clear()


def test_mask_secret():
    assert mask_secret("sk-abcdefghijklmnop") == "••••mnop"
    assert mask_secret("ab") == "••••"


def test_read_and_update_env(env_file: Path):
    values = read_env_values()
    assert values["OPENAI_API_KEY"] == "old-key"

    changed, error = update_env_values({"OPENAI_API_KEY": "sk-new-secret-key-abcdefgh"})
    assert error is None
    assert "OPENAI_API_KEY" in changed

    reloaded = read_env_values()
    assert reloaded["OPENAI_API_KEY"] == "sk-new-secret-key-abcdefgh"
    assert "OPENAI_MODEL" in reloaded

    content = env_file.read_text(encoding="utf-8")
    assert "sk-new-secret-key-abcdefgh" in content
    assert os.stat(env_file).st_mode & 0o777 == 0o600


def test_rejects_unknown_keys(env_file: Path):
    changed, error = update_env_values({"EVIL_KEY": "x"})
    assert changed == []
    assert error and "unknown_keys" in error


def test_normalize_openai_api_key():
    assert normalize_openai_api_key("  sk-test-key-with-enough-length  ") == "sk-test-key-with-enough-length"
    assert normalize_openai_api_key("Bearer sk-test-key-with-enough-length") == "sk-test-key-with-enough-length"
    assert normalize_openai_api_key('"sk-test-key-with-enough-length"') == "sk-test-key-with-enough-length"
    assert normalize_openai_api_key("sk-proj-\nabc\n") == "sk-proj-abc"


def test_rejects_invalid_openai_key_format(env_file: Path):
    changed, error = update_env_values({"OPENAI_API_KEY": "admin123456"})
    assert changed == []
    assert error == "openai_key_invalid_format"

    changed, error = update_env_values({"OPENAI_API_KEY": "sk-short"})
    assert changed == []
    assert error == "openai_key_too_short"

    changed, error = update_env_values({"OPENAI_API_KEY": "sk-valid-looking-test-key-xx"})
    assert error is None
    assert "OPENAI_API_KEY" in changed


def test_platform_env_path_uses_setting(tmp_path, monkeypatch):
    custom = tmp_path / "custom.env"
    monkeypatch.setenv("PLATFORM_ENV_FILE", str(custom))
    from app.core.config import get_settings

    get_settings.cache_clear()
    assert platform_env_path() == custom
    get_settings.cache_clear()


def test_allowed_keys_cover_openai():
    assert "OPENAI_API_KEY" in ALLOWED_KEYS
    assert "JWT_SECRET" in ALLOWED_KEYS
