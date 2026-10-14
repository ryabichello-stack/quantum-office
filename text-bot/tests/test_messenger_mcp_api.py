"""Unit tests for messenger MCP history helpers."""

from __future__ import annotations

from pathlib import Path

from session_store import append_message, init_db, list_sessions, load_history


def test_list_sessions_and_history(tmp_path: Path) -> None:
    db = tmp_path / "sessions.db"
    init_db(db)
    append_message(db, "telegram:111", {"role": "user", "content": "привет"})
    append_message(db, "telegram:111", {"role": "assistant", "content": "здравствуйте"})
    append_message(db, "max:222", {"role": "user", "content": "yo"})

    chats = list_sessions(db, limit=10)
    assert any(c["session_id"] == "telegram:111" for c in chats)
    tg = list_sessions(db, channel="telegram", limit=10)
    assert len(tg) == 1
    assert tg[0]["user_id"] == "111"

    hist = load_history(db, "telegram:111", limit=10)
    assert [m["content"] for m in hist] == ["привет", "здравствуйте"]
    assert all("created_at" in m for m in hist)
