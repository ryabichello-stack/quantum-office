"""Session login + token auth for Quantum Console."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("CONSOLE_TOKEN", "api-token-secret")
    monkeypatch.setenv("CONSOLE_USER", "admin")
    monkeypatch.setenv("CONSOLE_PASSWORD", "pass-secret")
    monkeypatch.setenv("CONSOLE_SESSION_SECRET", "session-hmac-secret")
    # Re-import after env so module constants pick up values
    import importlib
    import console.main as main

    importlib.reload(main)
    return TestClient(main.app)


def test_login_logout_session(client: TestClient):
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["authenticated"] is False

    bad = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert bad.status_code == 401

    ok = client.post("/api/auth/login", json={"username": "admin", "password": "pass-secret"})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert "qc_session" in ok.cookies

    me2 = client.get("/api/auth/me")
    assert me2.json()["authenticated"] is True
    assert me2.json()["user"] == "admin"
    assert me2.json()["via"] == "session"

    # Protected route works with cookie only
    # /api/status may 500 if host tools missing — auth must not be 401
    st = client.get("/api/status")
    assert st.status_code != 401

    out = client.post("/api/auth/logout")
    assert out.status_code == 200
    me3 = client.get("/api/auth/me")
    assert me3.json()["authenticated"] is False


def test_api_token_still_works(client: TestClient):
    r = client.get("/api/status", headers={"X-Console-Token": "api-token-secret"})
    assert r.status_code != 401

    bad = client.get("/api/status", headers={"X-Console-Token": "nope"})
    assert bad.status_code == 401
