"""Tests for /api/files/read text extraction."""

from __future__ import annotations

from fastapi.testclient import TestClient

import main
from models import FetchedFile


def test_files_read_utf8(monkeypatch):
    def fake_fetch(source, path, **kwargs):
        return FetchedFile(
            filename="note.txt",
            content="Привет компания".encode("utf-8"),
            content_type="text/plain",
            source=source,
            path=path,
        )

    monkeypatch.setattr(main.sources, "fetch", fake_fetch)
    monkeypatch.setattr(main, "WEBHOOK_TOKEN", "")
    client = TestClient(main.app)
    r = client.post("/api/files/read", json={"source": "mailru", "path": "/note.txt"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert "Привет" in data["text"]


def test_files_read_binary(monkeypatch):
    def fake_fetch(source, path, **kwargs):
        return FetchedFile(
            filename="x.pdf",
            content=b"%PDF-1.4\x00\xff\xfe",
            content_type="application/pdf",
            source=source,
            path=path,
        )

    monkeypatch.setattr(main.sources, "fetch", fake_fetch)
    monkeypatch.setattr(main, "WEBHOOK_TOKEN", "")
    client = TestClient(main.app)
    r = client.post("/api/files/read", json={"path": "/x.pdf"})
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert data["error"] == "binary_or_unsupported_encoding"
