"""P2.1 — self-service registration."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.auth import RegisterRequest, register
from app.models.tenant import Tenant
from app.models.user import User


def test_register_creates_tenant_and_token():
    db = MagicMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tenant = Tenant(slug="acme-corp", name="Acme Corp", public_key="pk_test123")
    tenant.id = tenant_id
    user = User(email="owner@acme.example", role="tenant_owner", tenant_id=tenant_id)
    user.id = user_id

    body = RegisterRequest(
        email="owner@acme.example",
        password="securepass1",
        company_name="Acme Corp",
    )

    with patch("app.api.v1.auth.register_tenant", return_value=(tenant, user, {"public_key": "pk_test123"})):
        with patch("app.api.v1.auth.create_access_token", return_value="jwt-token"):
            with patch("app.api.v1.auth.record_usage"):
                result = register(body=body, db=db)

    assert result.access_token == "jwt-token"
    assert result.tenant_slug == "acme-corp"
    assert result.public_key == "pk_test123"
    db.commit.assert_called_once()


def test_register_email_taken():
    db = MagicMock()
    body = RegisterRequest(
        email="taken@test.io",
        password="securepass1",
        company_name="Test Co",
    )

    with patch("app.api.v1.auth.register_tenant", side_effect=ValueError("email_taken")):
        with pytest.raises(HTTPException) as exc:
            register(body=body, db=db)

    assert exc.value.status_code == 409
