"""SQLite conversation history per session (channel:user_id)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_meta (
                    chat_id TEXT PRIMARY KEY,
                    scenario TEXT,
                    sticky INTEGER DEFAULT 0,
                    acl_role TEXT,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Migrate older DBs that lack acl_role
            cols = {
                str(r[1])
                for r in conn.execute("PRAGMA table_info(session_meta)").fetchall()
            }
            if "acl_role" not in cols:
                conn.execute("ALTER TABLE session_meta ADD COLUMN acl_role TEXT")
            conn.commit()
        finally:
            conn.close()


def get_session_meta(db_path: Path, chat_id: str) -> dict[str, Any]:
    with _lock:
        conn = _connect(db_path)
        try:
            row = conn.execute(
                "SELECT scenario, sticky, acl_role FROM session_meta WHERE chat_id = ?",
                (str(chat_id),),
            ).fetchone()
        finally:
            conn.close()
    if not row:
        return {"scenario": None, "sticky": False, "acl_role": None}
    return {
        "scenario": row["scenario"],
        "sticky": bool(row["sticky"]),
        "acl_role": (row["acl_role"] or None),
    }


def set_session_acl_role(db_path: Path, chat_id: str, acl_role: Optional[str]) -> None:
    """Persist unlocked role override (e.g. trainee). None clears it."""
    with _lock:
        conn = _connect(db_path)
        try:
            existing = conn.execute(
                "SELECT scenario, sticky FROM session_meta WHERE chat_id = ?",
                (str(chat_id),),
            ).fetchone()
            scenario = existing["scenario"] if existing else None
            sticky = int(existing["sticky"] or 0) if existing else 0
            if acl_role is None and scenario is None and not sticky:
                conn.execute("DELETE FROM session_meta WHERE chat_id = ?", (str(chat_id),))
            else:
                conn.execute(
                    """
                    INSERT INTO session_meta (chat_id, scenario, sticky, acl_role, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id) DO UPDATE SET
                      acl_role=excluded.acl_role,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (str(chat_id), scenario, sticky, acl_role),
                )
            conn.commit()
        finally:
            conn.close()


def set_session_scenario(
    db_path: Path,
    chat_id: str,
    scenario: Optional[str],
    *,
    sticky: bool = False,
) -> None:
    with _lock:
        conn = _connect(db_path)
        try:
            existing = conn.execute(
                "SELECT acl_role FROM session_meta WHERE chat_id = ?",
                (str(chat_id),),
            ).fetchone()
            acl_role = existing["acl_role"] if existing else None
            if scenario is None and not sticky and not acl_role:
                conn.execute("DELETE FROM session_meta WHERE chat_id = ?", (str(chat_id),))
            else:
                conn.execute(
                    """
                    INSERT INTO session_meta (chat_id, scenario, sticky, acl_role, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(chat_id) DO UPDATE SET
                      scenario=excluded.scenario,
                      sticky=excluded.sticky,
                      updated_at=CURRENT_TIMESTAMP
                    """,
                    (str(chat_id), scenario, 1 if sticky else 0, acl_role),
                )
            conn.commit()
        finally:
            conn.close()


def clear_chat(db_path: Path, chat_id: str) -> None:
    with _lock:
        conn = _connect(db_path)
        try:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (str(chat_id),))
            # keep sticky scenario preference across /reset
            conn.commit()
        finally:
            conn.close()


def _sanitize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop orphan tool rows / incomplete tool rounds (OpenAI rejects them)."""
    out: list[dict[str, Any]] = []
    pending_ids: set[str] = set()

    def _drop_incomplete_round() -> None:
        nonlocal pending_ids
        while out:
            last = out[-1]
            role = last.get("role")
            if role == "tool" or (role == "assistant" and last.get("tool_calls")):
                out.pop()
                if role == "assistant" and last.get("tool_calls"):
                    break
                continue
            break
        pending_ids.clear()

    for msg in messages:
        role = msg.get("role")
        if role == "tool":
            tcid = str(msg.get("tool_call_id") or "")
            if tcid and tcid in pending_ids:
                out.append(msg)
                pending_ids.discard(tcid)
            continue

        if role == "assistant" and msg.get("tool_calls"):
            if pending_ids:
                _drop_incomplete_round()
            pending_ids = {
                str(tc.get("id") or "")
                for tc in (msg.get("tool_calls") or [])
                if isinstance(tc, dict) and tc.get("id")
            }
            out.append(msg)
            continue

        if pending_ids:
            _drop_incomplete_round()
        out.append(msg)

    if pending_ids:
        _drop_incomplete_round()
    return out


def load_messages(db_path: Path, chat_id: str, *, limit: int = 40) -> list[dict[str, Any]]:
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
    return _sanitize_messages(out)


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
