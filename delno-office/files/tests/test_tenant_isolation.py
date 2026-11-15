"""Tenant A must not see tenant B's cloud listing, and env tokens stay opt-in."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import sources  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402


def setup_module() -> None:
    import os

    os.environ["FILES_MEMORY_BACKEND"] = "1"
    os.environ["YADISK_TOKEN"] = "env-token-should-not-leak"
    sources.seed_memory_listing(
        "token-a",
        [{"name": "a-only.txt", "path": "/a-only.txt", "type": "file"}],
    )
    sources.seed_memory_listing(
        "token-b",
        [{"name": "b-only.txt", "path": "/b-only.txt", "type": "file"}],
    )
    sources.seed_memory_listing(
        "env-token-should-not-leak",
        [{"name": "env-only.txt", "path": "/env-only.txt", "type": "file"}],
    )


def _names(response) -> list[str]:
    body = response.json()
    return [item["name"] for item in body.get("entries") or []]


def test_list_without_tenant_is_rejected():
    client = TestClient(main.app)
    response = client.post("/api/files/list", json={"source": "yadisk", "path": "/"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_required"


def test_mismatched_tenant_is_rejected():
    client = TestClient(main.app)
    response = client.post(
        "/api/files/list",
        json={
            "source": "yadisk",
            "path": "/",
            "tenant_id": "tenant-a",
            "credentials": {"token": "token-a"},
        },
        headers={"X-Tenant-Id": "tenant-b"},
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "tenant_mismatch"
    assert "a-only" not in response.text
    assert "b-only" not in response.text


def test_tenant_a_does_not_see_tenant_b_files():
    client = TestClient(main.app)
    first = client.post(
        "/api/files/list",
        json={
            "source": "yadisk",
            "path": "/",
            "tenant_id": "tenant-a",
            "credentials": {"token": "token-a"},
        },
    )
    second = client.post(
        "/api/files/list",
        json={
            "source": "yadisk",
            "path": "/",
            "tenant_id": "tenant-b",
            "credentials": {"token": "token-b"},
        },
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert _names(first) == ["a-only.txt"]
    assert _names(second) == ["b-only.txt"]
    assert "env-token" not in first.text


def test_env_token_is_not_used_without_explicit_flag():
    client = TestClient(main.app)
    response = client.post(
        "/api/files/list",
        json={"source": "yadisk", "path": "/", "tenant_id": "tenant-a"},
    )
    assert response.status_code == 400
    assert "env-only" not in response.text
    assert "env-token" not in response.text


def test_env_fallback_only_when_flag_set():
    client = TestClient(main.app)
    response = client.post(
        "/api/files/list",
        json={
            "source": "yadisk",
            "path": "/",
            "tenant_id": "service-tenant",
            "allow_env_fallback": True,
        },
    )
    assert response.status_code == 200
    assert _names(response) == ["env-only.txt"]
