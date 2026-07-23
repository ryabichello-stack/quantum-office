"""browse_files formatting and tool wiring."""

from __future__ import annotations

import json

import ava_client as ac


def test_format_files_browse_lists_dirs_and_files():
    msg = ac._format_files_browse(
        {
            "source": "mailru",
            "path": "/",
            "account": "office@quantumlabs.ru",
            "dirs": [
                {
                    "name": "Docs",
                    "path": "/Docs",
                    "modified_at": "2025-01-01 12:00 UTC",
                }
            ],
            "files": [
                {
                    "name": "deck.pdf",
                    "path": "/deck.pdf",
                    "bytes": 2048,
                    "created_at": "2024-11-15 08:00 UTC",
                    "modified_at": "2025-01-02 15:30 UTC",
                }
            ],
        }
    )
    assert "Mail.ru" in msg
    assert "Docs" in msg
    assert "deck.pdf" in msg
    assert "/Docs" in msg
    assert "созд." in msg or "изм." in msg


def test_search_files_calls_search_api(monkeypatch):
    def fake_post(url, body, timeout=20.0, brain_principal=None):
        assert url.endswith("/api/files/search")
        assert body["query"] == "банк"
        return {
            "ok": True,
            "mode": "search",
            "query": "банк",
            "source": "mailru",
            "path": "/",
            "dirs": [{"name": "!Банк", "path": "/!Банк", "type": "dir"}],
            "files": [],
            "entries": [{"name": "!Банк", "path": "/!Банк", "type": "dir"}],
            "counts": {"dirs": 1, "files": 0, "total": 1},
        }

    monkeypatch.setattr(ac, "_post_json", fake_post)
    out = json.loads(
        ac.run_tool("search_files", {"query": "банк"}, role="owner")
    )
    assert out["ok"] is True
    assert "!Банк" in out["owner_message"]
    assert "Поиск" in out["owner_message"]


def test_browse_files_calls_list_api(monkeypatch):
    monkeypatch.setattr(ac, "FILES_BASE", "http://127.0.0.1:8015")

    def fake_post(url, body, timeout=20.0, brain_principal=None):
        assert url.endswith("/api/files/list")
        assert body == {"source": "mailru", "path": "/"}
        return {
            "ok": True,
            "source": "mailru",
            "path": "/",
            "account": "office@quantumlabs.ru",
            "dirs": [{"name": "Docs", "path": "/Docs", "type": "dir"}],
            "files": [],
            "entries": [{"name": "Docs", "path": "/Docs", "type": "dir"}],
            "counts": {"dirs": 1, "files": 0, "total": 1},
        }

    monkeypatch.setattr(ac, "_post_json", fake_post)
    out = json.loads(ac.run_tool("browse_files", {}, role="owner"))
    assert out["ok"] is True
    assert "Docs" in out["owner_message"]
    assert "instruction_for_assistant" in out
