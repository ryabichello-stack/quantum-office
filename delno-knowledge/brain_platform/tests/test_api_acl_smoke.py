"""HTTP smoke tests for /api/brain/search — tenant headers and ACL."""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from brain_platform.db.connection import init_db
from brain_platform.db.factory import reset_repo_singleton
from brain_platform.db.repository import BrainRepository
from brain_platform.tests.conftest import (
    MARKER_A,
    MARKER_B,
    PUBLIC_MARKER_A,
    TENANT_A,
    TENANT_B,
    seed_company_secret,
    seed_public_faq,
)


@pytest.fixture()
def brain_client(tmp_path: Path, monkeypatch):
    db = tmp_path / "brain-api.db"
    monkeypatch.setenv("BRAIN_DB_PATH", str(db))
    monkeypatch.setenv("BRAIN_ENABLED", "true")
    monkeypatch.setenv("BRAIN_TENANT_ID", TENANT_A)

    reset_repo_singleton()
    import brain_platform.api.router as router_mod

    router_mod._repo = None
    router_mod._search = None

    repo = BrainRepository(init_db(db))
    seed_company_secret(repo, tenant_id=TENANT_A, marker=MARKER_A)
    seed_company_secret(repo, tenant_id=TENANT_B, marker=MARKER_B)
    seed_public_faq(repo, tenant_id=TENANT_A, marker=PUBLIC_MARKER_A)

    main_mod = importlib.import_module("main_delno")
    importlib.reload(main_mod)
    client = TestClient(main_mod.app)
    yield client
    client.close()
    reset_repo_singleton()
    router_mod._repo = None
    router_mod._search = None


def _search(
    client: TestClient,
    *,
    query: str,
    tenant_id: str,
    principal_id: str,
    body_tenant: str | None = None,
):
    payload = {"query": query, "mode": "keyword", "limit": 8}
    if body_tenant is not None:
        payload["tenant_id"] = body_tenant
    return client.post(
        "/api/brain/search",
        json=payload,
        headers={
            "X-Tenant-Id": tenant_id,
            "X-Principal-Id": principal_id,
        },
    )


class TestBrainSearchHTTP:
    def test_owner_finds_own_tenant_marker(self, brain_client: TestClient):
        response = _search(
            brain_client,
            query=MARKER_A,
            tenant_id=TENANT_A,
            principal_id="service:text-owner",
        )
        assert response.status_code == 200
        assert MARKER_A in (response.json().get("text") or "")

    def test_owner_cannot_read_other_tenant_marker(self, brain_client: TestClient):
        response = _search(
            brain_client,
            query=MARKER_B,
            tenant_id=TENANT_A,
            principal_id="service:text-owner",
        )
        assert response.status_code == 200
        assert MARKER_B not in (response.json().get("text") or "")

    def test_guest_reads_public_not_company(self, brain_client: TestClient):
        public = _search(
            brain_client,
            query=PUBLIC_MARKER_A,
            tenant_id=TENANT_A,
            principal_id="service:text-guest",
        )
        company = _search(
            brain_client,
            query=MARKER_A,
            tenant_id=TENANT_A,
            principal_id="service:text-guest",
        )
        assert public.status_code == 200
        assert company.status_code == 200
        assert PUBLIC_MARKER_A in (public.json().get("text") or "")
        assert MARKER_A not in (company.json().get("text") or "")

    def test_body_tenant_mismatch_returns_403(self, brain_client: TestClient):
        response = _search(
            brain_client,
            query=MARKER_A,
            tenant_id=TENANT_A,
            principal_id="service:text-owner",
            body_tenant=TENANT_B,
        )
        assert response.status_code == 403
