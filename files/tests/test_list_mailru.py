"""Unit tests for Mail.ru WebDAV listing parser."""

from __future__ import annotations

import sources


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
