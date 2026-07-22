"""Reply inbox: classification + unprocessed queue for managers."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext
from modules.replies.classify import ReplyClass, classify_reply

logger = logging.getLogger("ava-outreach.replies")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ReplyInboxStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or MODULES_DB)
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
                CREATE TABLE IF NOT EXISTS reply_inbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    from_email TEXT NOT NULL,
                    subject TEXT,
                    preview TEXT,
                    classification TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0,
                    should_stop INTEGER NOT NULL DEFAULT 0,
                    should_notify INTEGER NOT NULL DEFAULT 0,
                    should_create_task INTEGER NOT NULL DEFAULT 0,
                    outbox_id INTEGER,
                    company_id TEXT,
                    deal_id TEXT,
                    processed INTEGER NOT NULL DEFAULT 0,
                    processed_at TEXT,
                    bitrix_task_id TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_reply_inbox_unprocessed "
                "ON reply_inbox(processed, created_at)"
            )

    def add(
        self,
        *,
        message_id: str,
        from_email: str,
        subject: str,
        preview: str,
        classified: ReplyClass,
        outbox_id: int | None = None,
        company_id: str | None = None,
        deal_id: str | None = None,
    ) -> dict[str, Any] | None:
        mid = (message_id or "").strip().lower()
        if not mid:
            return None
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO reply_inbox(
                    message_id, from_email, subject, preview,
                    classification, confidence, should_stop, should_notify,
                    should_create_task, outbox_id, company_id, deal_id,
                    processed, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    mid,
                    (from_email or "").strip().lower(),
                    subject,
                    (preview or "")[:4000],
                    classified.classification,
                    float(classified.confidence),
                    1 if classified.should_stop_sequence else 0,
                    1 if classified.should_notify else 0,
                    1 if classified.should_create_task else 0,
                    outbox_id,
                    company_id,
                    deal_id,
                    0
                    if classified.classification
                    in (
                        "human_unclassified",
                        "positive_interest",
                        "forwarded",
                        "negative",
                    )
                    else 1,  # auto/ooo/bounce auto-processed
                    _utc_now(),
                ),
            )
            if not cur.rowcount:
                row = conn.execute(
                    "SELECT * FROM reply_inbox WHERE message_id = ?", (mid,)
                ).fetchone()
                return dict(row) if row else None
            rid = int(cur.lastrowid)
        return self.get(rid)

    def get(self, rid: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM reply_inbox WHERE id = ?", (rid,)
            ).fetchone()
        return dict(row) if row else None

    def list_unprocessed(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reply_inbox
                WHERE processed = 0
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reply_inbox
                ORDER BY created_at DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_processed(self, rid: int, *, bitrix_task_id: str | None = None) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE reply_inbox
                SET processed=1, processed_at=?, bitrix_task_id=COALESCE(?, bitrix_task_id)
                WHERE id=?
                """,
                (_utc_now(), bitrix_task_id, rid),
            )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM reply_inbox").fetchone()["n"]
            open_n = conn.execute(
                "SELECT COUNT(*) AS n FROM reply_inbox WHERE processed = 0"
            ).fetchone()["n"]
        return {"total": int(total), "unprocessed": int(open_n)}


class RepliesModule:
    name = "replies"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = ReplyInboxStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["reply_inbox"] = self.store
        logger.info("replies module ready %s", self.store.counts())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, **self.store.counts()}

    def register_routes(self, router: Any) -> None:
        @router.get("/inbox")
        def inbox(unprocessed_only: bool = True, limit: int = 50) -> dict[str, Any]:
            items = (
                self.store.list_unprocessed(limit)
                if unprocessed_only
                else self.store.list_recent(limit)
            )
            return {"ok": True, "counts": self.store.counts(), "items": items}

        @router.post("/inbox/{rid}/processed")
        def mark(rid: int) -> dict[str, Any]:
            self.store.mark_processed(rid)
            return {"ok": True}
