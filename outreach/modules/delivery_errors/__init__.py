"""Delivery Error Analyzer — idempotent SMTP/DSN event log + actions."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext
from modules.deliverability.bounce import BounceClass, classify_bounce

logger = logging.getLogger("ava-outreach.delivery_errors")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def event_fingerprint(
    *,
    message_id: str,
    email: str,
    smtp_code: str,
    category: str,
    raw: str,
) -> str:
    base = "|".join(
        [
            (message_id or "").strip().lower(),
            (email or "").strip().lower(),
            (smtp_code or "").strip(),
            (category or "").strip(),
            hashlib.sha256((raw or "")[:500].encode("utf-8", "ignore")).hexdigest()[:16],
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


class DeliveryErrorStore:
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
                CREATE TABLE IF NOT EXISTS delivery_error_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    account_id TEXT,
                    from_domain TEXT,
                    provider TEXT,
                    campaign TEXT,
                    message_id TEXT,
                    outreach_id TEXT,
                    recipient_email TEXT NOT NULL,
                    smtp_code TEXT NOT NULL DEFAULT '',
                    enhanced_code TEXT NOT NULL DEFAULT '',
                    smtp_stage TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL,
                    raw_text TEXT,
                    decision TEXT NOT NULL DEFAULT '',
                    retryable INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delivery_errors_created
                ON delivery_error_events(created_at)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_delivery_errors_cat
                ON delivery_error_events(category, created_at)
                """
            )

    def record(
        self,
        *,
        email: str,
        raw: str | None,
        classified: BounceClass | None = None,
        message_id: str = "",
        outreach_id: str = "",
        account_id: str = "legacy",
        from_domain: str = "",
        provider: str = "",
        campaign: str = "",
        smtp_stage: str = "dsn",
        decision: str = "",
    ) -> dict[str, Any]:
        """Insert once; duplicate fingerprints are no-ops (idempotent)."""
        classified = classified or classify_bounce(raw)
        fp = event_fingerprint(
            message_id=message_id,
            email=email,
            smtp_code=classified.code,
            category=classified.category,
            raw=raw or "",
        )
        decision = decision or self.default_decision(classified)
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT id, decision FROM delivery_error_events WHERE fingerprint = ?",
                (fp,),
            ).fetchone()
            if existing:
                return {
                    "ok": True,
                    "duplicate": True,
                    "id": int(existing["id"]),
                    "decision": str(existing["decision"]),
                    "category": classified.category,
                    "classified": classified,
                }
            cur = conn.execute(
                """
                INSERT INTO delivery_error_events(
                    fingerprint, created_at, account_id, from_domain, provider,
                    campaign, message_id, outreach_id, recipient_email,
                    smtp_code, enhanced_code, smtp_stage, category, raw_text,
                    decision, retryable
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fp,
                    _utc_now(),
                    account_id,
                    from_domain,
                    provider,
                    campaign,
                    message_id,
                    outreach_id,
                    (email or "").strip().lower(),
                    classified.code,
                    classified.code,
                    smtp_stage,
                    classified.category,
                    (raw or "")[:2000],
                    decision,
                    1 if classified.retry else 0,
                ),
            )
            return {
                "ok": True,
                "duplicate": False,
                "id": int(cur.lastrowid or 0),
                "decision": decision,
                "category": classified.category,
                "classified": classified,
            }

    @staticmethod
    def default_decision(classified: BounceClass) -> str:
        if classified.category == "policy":
            return "cool_recipient_isp;no_retry;alert"
        if classified.category == "auth":
            return "pause_route;no_retry;alert"
        if classified.category == "hard":
            return "suppress_recipient;no_retry"
        if classified.category == "soft":
            return "limited_retry_backoff"
        if classified.category == "unknown":
            return "suppress_conservative;no_retry"
        return "log_only"

    def list_recent(self, *, limit: int = 50, category: str | None = None) -> list[dict[str, Any]]:
        with self.connect() as conn:
            if category:
                rows = conn.execute(
                    """
                    SELECT * FROM delivery_error_events
                    WHERE category = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (category, max(1, min(limit, 500))),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM delivery_error_events
                    ORDER BY id DESC LIMIT ?
                    """,
                    (max(1, min(limit, 500)),),
                ).fetchall()
        return [dict(r) for r in rows]

    def counts_today(self) -> dict[str, int]:
        day = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT category, COUNT(*) AS n
                FROM delivery_error_events
                WHERE created_at LIKE ?
                GROUP BY category
                """,
                (f"{day}%",),
            ).fetchall()
        return {str(r["category"]): int(r["n"]) for r in rows}


class DeliveryErrorsModule:
    name = "delivery_errors"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = DeliveryErrorStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["delivery_errors"] = self.store
        logger.info("delivery_errors module ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "today": self.store.counts_today()}

    def register_routes(self, router: Any) -> None:
        @router.get("/events")
        def events(limit: int = 50, category: str | None = None) -> dict[str, Any]:
            return {
                "ok": True,
                "today": self.store.counts_today(),
                "items": self.store.list_recent(limit=limit, category=category),
            }
