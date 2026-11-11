"""Google Drive + OneDrive sources — tools-first (no tokens required for surfaces)."""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO

import pytest

import sources


class _Resp:
    def __init__(self, payload, *, headers=None):
        if isinstance(payload, (dict, list)):
            self._raw = json.dumps(payload).encode("utf-8")
        elif isinstance(payload, bytes):
            self._raw = payload
        else:
            self._raw = str(payload).encode("utf-8")
        self.headers = headers or {"Content-Type": "application/json"}

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_sources_status_lists_gdrive_onedrive():
    st = sources.sources_status()
    assert "gdrive" in st["list_sources"]
    assert "onedrive" in st["list_sources"]
    assert st["gdrive_configured"] is False
    assert st["onedrive_configured"] is False
    assert st["creds_policy"] == "tools_first"


def test_gdrive_not_configured():
    with pytest.raises(sources.SourceError) as exc:
        sources.list_gdrive("/")
    assert exc.value.code == "gdrive_not_configured"


def test_onedrive_not_configured():
    with pytest.raises(sources.SourceError) as exc:
        sources.fetch_onedrive("/docs/a.pdf")
    assert exc.value.code == "onedrive_not_configured"


def test_fetch_dispatch_unknown():
    with pytest.raises(sources.SourceError) as exc:
        sources.fetch("dropbox", "/x")
    assert exc.value.code == "unknown_source"


def test_gdrive_list_and_fetch(monkeypatch):
    monkeypatch.setattr(sources, "GOOGLE_DRIVE_TOKEN", "tok")

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req.get_full_url())
        if "alt=media" in url:
            return _Resp(b"%PDF-demo", headers={"Content-Type": "application/pdf"})
        if "/files?" in url and "q=" in url:
            return _Resp(
                {
                    "files": [
                        {
                            "id": "folder1",
                            "name": "Docs",
                            "mimeType": "application/vnd.google-apps.folder",
                        },
                        {
                            "id": "file1",
                            "name": "pitch.pdf",
                            "mimeType": "application/pdf",
                            "size": "12",
                        },
                    ]
                }
            )
        if "/files/file1" in url:
            return _Resp(
                {
                    "id": "file1",
                    "name": "pitch.pdf",
                    "mimeType": "application/pdf",
                    "size": "12",
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    entries = sources.list_gdrive("/")
    assert {e.name for e in entries} == {"Docs", "pitch.pdf"}
    assert any(e.type == "dir" for e in entries)

    f = sources.fetch_gdrive("id:file1")
    assert f.filename == "pitch.pdf"
    assert f.content.startswith(b"%PDF")
    assert f.source == "gdrive"


def test_onedrive_list_and_fetch(monkeypatch):
    monkeypatch.setattr(sources, "ONEDRIVE_TOKEN", "tok")

    def fake_urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req.get_full_url())
        if url.endswith("/content") or ":/content" in url:
            return _Resp(b"hello-one", headers={"Content-Type": "text/plain"})
        if url.endswith("/children") or ":/children" in url:
            return _Resp(
                {
                    "value": [
                        {"name": "FolderA", "folder": {}, "size": 0},
                        {"name": "note.txt", "size": 9, "file": {}},
                    ]
                }
            )
        raise AssertionError(url)

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    entries = sources.list_onedrive("/")
    assert entries[0].type == "dir"
    assert entries[1].name == "note.txt"
    f = sources.fetch_onedrive("/note.txt")
    assert f.content == b"hello-one"
    assert f.source == "onedrive"


def test_search_dispatch(monkeypatch):
    monkeypatch.setattr(sources, "GOOGLE_DRIVE_TOKEN", "tok")

    def fake_urlopen(req, timeout=None):
        return _Resp({"files": [{"id": "1", "name": "alpha.pdf", "mimeType": "application/pdf"}]})

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    hits = sources.search_entries("gdrive", "alpha")
    assert hits[0].path == "id:1"
