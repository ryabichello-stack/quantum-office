"""Admin platform secrets API."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.admin_settings import (
    OpenAiKeyTestRequest,
    PlatformSecretsUpdate,
    get_platform_secrets,
    patch_platform_secrets,
    verify_platform_openai_key,
)
from app.models.user import User
from app.services.rate_limit import get_widget_rate_limiter


@pytest.fixture
def platform_admin():
    return User(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="admin@dlno.ru",
        role="platform_admin",
        password_hash="x",
    )


def test_get_platform_secrets_masked(platform_admin):
    with patch("app.api.v1.admin_settings.env_file_status", return_value={"path": "/opt/delno/.env", "exists": True, "writable": True}):
        with patch("app.api.v1.admin_settings.list_secret_fields", return_value=[{"id": "openai", "title": "OpenAI", "items": []}]):
            result = get_platform_secrets(admin=platform_admin)
    assert result["env_file"]["path"] == "/opt/delno/.env"
    assert "groups" in result


def test_patch_platform_secrets(platform_admin):
    db = MagicMock()
    body = PlatformSecretsUpdate(values={"OPENAI_API_KEY": "sk-test"})
    with patch("app.api.v1.admin_settings.env_file_status", return_value={"path": "/opt/delno/.env", "exists": True, "writable": True}):
        with patch("app.api.v1.admin_settings.update_env_values", return_value=(["OPENAI_API_KEY"], None)):
            with patch("app.api.v1.admin_settings.write_audit"):
                with patch("app.api.v1.admin_settings.emit_event"):
                    with patch("app.api.v1.admin_settings.list_secret_fields", return_value=[]):
                        result = patch_platform_secrets(body=body, db=db, admin=platform_admin)
    assert result["ok"] is True
    assert "OPENAI_API_KEY" in result["changed"]
    db.commit.assert_called_once()


def test_patch_platform_secrets_not_writable(platform_admin):
    db = MagicMock()
    body = PlatformSecretsUpdate(values={"OPENAI_API_KEY": "sk-test-key-long-enough-xx"})
    with patch("app.api.v1.admin_settings.env_file_status", return_value={"writable": False}):
        with pytest.raises(HTTPException) as exc:
            patch_platform_secrets(body=body, db=db, admin=platform_admin)
    assert exc.value.status_code == 503


def test_test_platform_openai_key(platform_admin):
    with patch(
        "app.api.v1.admin_settings.verify_openai_api_key",
        return_value={"ok": True, "key_preview": "••••abcd", "realtime_models_count": 3, "chat_models_count": 5},
    ):
        result = verify_platform_openai_key(
            body=OpenAiKeyTestRequest(api_key="sk-test-key-long-enough-xx"),
            admin=platform_admin,
        )
    assert result["ok"] is True


def test_test_platform_openai_key_rejects_bad_format(platform_admin):
    with pytest.raises(HTTPException) as exc:
        verify_platform_openai_key(body=OpenAiKeyTestRequest(api_key="admin123456"), admin=platform_admin)
    assert exc.value.status_code == 400
    assert exc.value.detail == "openai_key_invalid_format"
