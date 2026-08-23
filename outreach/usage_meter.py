"""Lightweight usage metering (Stage 8 / P3 lite) — local counters only."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


class UsageMeter:
    def __init__(self, db_path: Path | None = None, *, tenant_id: str = "quantum-labs") -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.tenant_id = tenant_id
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS usage_meters (
                    tenant_id TEXT NOT NULL,
                    day TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    value REAL NOT NULL DEFAULT 0,
                    PRIMARY KEY (tenant_id, day, metric)
                )
                """
            )

    def incr(self, metric: str, amount: float = 1.0) -> None:
        day = _utc_day()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO usage_meters(tenant_id, day, metric, value)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tenant_id, day, metric) DO UPDATE SET
                    value = value + excluded.value
                """,
                (self.tenant_id, day, metric, float(amount)),
            )

    def snapshot(self, *, days: int = 14) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT day, metric, value FROM usage_meters
                WHERE tenant_id = ?
                ORDER BY day DESC, metric ASC
                LIMIT ?
                """,
                (self.tenant_id, max(1, min(days * 20, 500))),
            ).fetchall()
        return {
            "ok": True,
            "tenant_id": self.tenant_id,
            "items": [dict(r) for r in rows],
        }
