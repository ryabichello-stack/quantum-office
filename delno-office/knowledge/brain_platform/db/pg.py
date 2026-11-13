"""Postgres connection helpers for Second Brain."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_SCHEMA_PG = Path(__file__).with_name("schema_postgres.sql")


def database_url() -> str:
    return (os.getenv("BRAIN_DATABASE_URL") or "").strip()


def store_backend() -> str:
    """sqlite | postgres — which store the API/CLI use."""
    raw = (os.getenv("BRAIN_STORE") or "sqlite").strip().lower()
    if raw in ("pg", "postgres", "postgresql"):
        return "postgres"
    return "sqlite"


def connect_postgres(url: str | None = None):
    import psycopg
    from psycopg.rows import dict_row

    dsn = url or database_url()
    if not dsn:
        raise RuntimeError("BRAIN_DATABASE_URL is not set")
    conn = psycopg.connect(dsn, row_factory=dict_row, autocommit=False)
    return conn


def init_postgres(url: str | None = None):
    conn = connect_postgres(url)
    sql = _SCHEMA_PG.read_text(encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    return conn


def ensure_hnsw_index(conn) -> dict[str, Any]:
    """Create HNSW index when enough embedded rows exist."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM chunks WHERE embedding IS NOT NULL"
        )
        n = int(cur.fetchone()["n"])
        if n < 50:
            return {"ok": True, "skipped": True, "reason": "too_few_vectors", "count": n}
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw
            ON chunks USING hnsw (embedding vector_cosine_ops)
            """
        )
    conn.commit()
    return {"ok": True, "skipped": False, "count": n}
