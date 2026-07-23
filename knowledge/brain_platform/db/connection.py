"""SQLite connection for Second Brain (Postgres URL reserved for later migration)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

_SCHEMA = Path(__file__).with_name("schema.sql")


def default_db_path() -> Path:
    raw = os.getenv("BRAIN_DB_PATH", "").strip()
    if raw:
        return Path(raw)
    data = os.getenv("BRAIN_DATA_DIR", "").strip() or os.getenv("DATA_DIR", "").strip()
    if data:
        return Path(data) / "brain.db"
    # Local default under knowledge/data (gitignored)
    return Path(__file__).resolve().parents[2] / "data" / "brain.db"


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db(conn: sqlite3.Connection | Path | str | None = None) -> sqlite3.Connection:
    if isinstance(conn, (str, Path)):
        conn = connect(conn)
        own = True
    elif conn is None:
        conn = connect()
        own = True
    else:
        own = False
    sql = _SCHEMA.read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.execute(
        "INSERT OR IGNORE INTO meta(key, value) VALUES ('schema_version', '1')"
    )
    conn.commit()
    return conn
