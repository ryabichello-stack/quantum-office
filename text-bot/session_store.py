"""SQLite conversation history per session (channel:user_id)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT,
                    tool_calls TEXT,
                    tool_call_id TEXT,
                    name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_id ON chat_messages(chat_id)"
            )
            conn.commit()
        finally:
            conn.close()


def load_messages(db_path: Path, chat_id: str, *, limit: int = 24) -> list[dict[str, Any]]:
    with _lock:
        conn = _connect(db_path)
        try:
            rows = conn.execute(
                """
                SELECT role, content, tool_calls, tool_call_id, name
                FROM chat_messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (str(chat_id), int(limit)),
            ).fetchall()
        finally:
            conn.close()

    out: list[dict[str, Any]] = []
    for row in reversed(rows):
        msg: dict[str, Any] = {"role": row["role"]}
        if row["content"]:
            msg["content"] = row["content"]
        if row["tool_calls"]:
            msg["tool_calls"] = json.loads(row["tool_calls"])
        if row["tool_call_id"]:
            msg["tool_call_id"] = row["tool_call_id"]
        if row["name"]:
            msg["name"] = row["name"]
        out.append(msg)
    return out


def append_message(db_path: Path, chat_id: str, message: dict[str, Any]) -> None:
    tool_calls = message.get("tool_calls")
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute(
                """
                INSERT INTO chat_messages (chat_id, role, content, tool_calls, tool_call_id, name)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(chat_id),
                    message.get("role", "user"),
                    message.get("content"),
                    json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None,
                    message.get("tool_call_id"),
                    message.get("name"),
                ),
            )
            conn.commit()
        finally:
            conn.close()


def clear_chat(db_path: Path, chat_id: str) -> None:
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (str(chat_id),))
            conn.commit()
        finally:
            conn.close()
