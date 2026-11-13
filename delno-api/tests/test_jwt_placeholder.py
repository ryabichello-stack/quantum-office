"""JWT must not sign with an empty secret or a known placeholder."""

from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import jwt_signing_key


@pytest.fixture()
def _clear_settings():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.parametrize(
    "value",
    ["", "change-me", "change-me-in-production", "change-me-long-random", "dev-secret", "changeme123"],
)
def test_jwt_placeholder_rejected(monkeypatch, _clear_settings, value):
    monkeypatch.setenv("JWT_SECRET", value)
    get_settings.cache_clear()
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        jwt_signing_key()


def test_jwt_real_secret_accepted(monkeypatch, _clear_settings):
    monkeypatch.setenv("JWT_SECRET", "unit-test-secret-not-a-placeholder")
    get_settings.cache_clear()
    assert jwt_signing_key() == "unit-test-secret-not-a-placeholder"
