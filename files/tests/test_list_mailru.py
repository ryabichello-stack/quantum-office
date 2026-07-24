"""Unit tests for Mail.ru WebDAV listing parser."""

from __future__ import annotations

import sources
from models import ListedEntry


SAMPLE_PROPFIND = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
        <d:displayname>root</d:displayname>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/Docs/</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype><d:collection/></d:resourcetype>
        <d:displayname>Docs</d:displayname>
        <d:getlastmodified>Wed, 01 Jan 2025 12:00:00 GMT</d:getlastmodified>
        <d:creationdate>2024-12-01T10:00:00Z</d:creationdate>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
  <d:response>
    <d:href>/deck.pdf</d:href>
    <d:propstat>
      <d:prop>
        <d:resourcetype/>
        <d:displayname>deck.pdf</d:displayname>
        <d:getcontentlength>2048</d:getcontentlength>
        <d:getlastmodified>Thu, 02 Jan 2025 15:30:00 GMT</d:getlastmodified>
        <d:creationdate>2024-11-15T08:00:00Z</d:creationdate>
      </d:prop>
      <d:status>HTTP/1.1 200 OK</d:status>
    </d:propstat>
  </d:response>
</d:multistatus>
"""


class _Resp:
    def __init__(self, data: bytes):
        self._data = data

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_list_mailru_parses_dirs_and_files(monkeypatch):
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_USER", "office@quantumlabs.ru")
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_PASSWORD", "secret")

    def fake_urlopen(req, timeout=60):
        assert req.get_method() == "PROPFIND"
        assert req.get_header("Depth") == "1"
        return _Resp(SAMPLE_PROPFIND)

    monkeypatch.setattr(sources.urllib.request, "urlopen", fake_urlopen)
    entries = sources.list_mailru("/")
    assert [e.name for e in entries if e.type == "dir"] == ["Docs"]
    files = [e for e in entries if e.type == "file"]
    assert len(files) == 1
    assert files[0].name == "deck.pdf"
    assert files[0].bytes == 2048
    assert files[0].path == "/deck.pdf"
    assert files[0].modified_at
    assert files[0].created_at
    dirs = [e for e in entries if e.type == "dir"]
    assert dirs[0].modified_at


def test_search_mailru_filters_by_name(monkeypatch):
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_USER", "office@quantumlabs.ru")
    monkeypatch.setattr(sources, "MAILRU_WEBDAV_PASSWORD", "secret")
    monkeypatch.setattr(
        sources,
        "list_mailru",
        lambda path="/": [
            ListedEntry(name="Docs", path="/Docs", type="dir"),
            ListedEntry(name="deck.pdf", path="/deck.pdf", type="file", bytes=1),
            ListedEntry(name="other.txt", path="/other.txt", type="file", bytes=2),
        ]
        if path in ("/",)
        else [],
    )
    hits = sources.search_mailru("deck", path="/", limit=10)
    assert [h.name for h in hits] == ["deck.pdf"]
