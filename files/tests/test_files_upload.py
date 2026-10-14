"""Unit tests for /api/files/upload (mocked WebDAV)."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

import sources
from main import app


client = TestClient(app)


def test_upload_requires_content(monkeypatch):
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_USER", "u@x.ru")
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_PASSWORD", "secret")
    r = client.post("/api/files/upload", json={"path": "/MCP/a.txt"})
    assert r.status_code == 400


def test_upload_text_ok(monkeypatch):
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_USER", "u@x.ru")
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_PASSWORD", "secret")

    def fake_upload(source, path, content, **kwargs):
        assert source == "mailru"
        assert path == "/MCP/memo.txt"
        assert content == b"hello"
        return {
            "ok": True,
            "source": "mailru",
            "path": path,
            "filename": "memo.txt",
            "bytes": len(content),
            "content_type": "text/plain",
            "account": "u@x.ru",
        }

    monkeypatch.setattr(sources, "upload_file", fake_upload)
    r = client.post(
        "/api/files/upload",
        json={"path": "/MCP/memo.txt", "text": "hello", "source": "mailru"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["path"] == "/MCP/memo.txt"
    assert body["bytes"] == 5


def test_upload_base64_ok(monkeypatch):
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_USER", "u@x.ru")
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_PASSWORD", "secret")

    def fake_upload(source, path, content, **kwargs):
        assert content == b"%PDF-1.4"
        return {
            "ok": True,
            "source": "mailru",
            "path": path,
            "filename": "x.pdf",
            "bytes": len(content),
            "content_type": "application/pdf",
            "account": "u@x.ru",
        }

    monkeypatch.setattr(sources, "upload_file", fake_upload)
    r = client.post(
        "/api/files/upload",
        json={
            "path": "/MCP/x.pdf",
            "content_base64": base64.b64encode(b"%PDF-1.4").decode(),
            "content_type": "application/pdf",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
