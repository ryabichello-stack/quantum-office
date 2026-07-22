"""SQLite outbox: unique email, send status lifecycle."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

Status = Literal[
    "pending",
    "sending",
    "sent",
    "failed",
    "skipped",
    "dry_run",
    "replied",
    "bounced",
    "cancelled",
]


@dataclass
class OutboxRow:
    id: int
    email: str
    company_id: str
    contact_id: str
    contact_name: str
    status: str
    attempts: int
    last_error: str | None
    sent_at: str | None
    deal_id: str | None
    message_id: str | None
    created_at: str
    updated_at: str


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class OutboxStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
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
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    company_id TEXT NOT NULL DEFAULT '',
                    contact_id TEXT NOT NULL DEFAULT '',
                    contact_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    sent_at TEXT,
                    deal_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_outbox_status ON outbox(status)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS inbound_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL UNIQUE,
                    from_email TEXT NOT NULL,
                    subject TEXT,
                    outbox_id INTEGER,
                    deal_id TEXT,
                    notified INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            # Lightweight migrations for DBs created before company/deal columns.
            cols = {r[1] for r in conn.execute("PRAGMA table_info(outbox)").fetchall()}
            if "company_id" not in cols:
                conn.execute(
                    "ALTER TABLE outbox ADD COLUMN company_id TEXT NOT NULL DEFAULT ''"
                )
            if "deal_id" not in cols:
                conn.execute("ALTER TABLE outbox ADD COLUMN deal_id TEXT")
            if "replied_at" not in cols:
                conn.execute("ALTER TABLE outbox ADD COLUMN replied_at TEXT")
            if "message_id" not in cols:
                conn.execute("ALTER TABLE outbox ADD COLUMN message_id TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_outbox_message_id ON outbox(message_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_outbox_company ON outbox(company_id)"
            )

    def upsert_company(
        self,
        *,
        email: str,
        company_id: str,
        company_title: str,
    ) -> bool:
        """Insert pending row for a company email. True if inserted."""
        now = _utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO outbox
                    (email, company_id, contact_id, contact_name, status, created_at, updated_at)
                VALUES (?, ?, '', ?, 'pending', ?, ?)
                """,
                (email, str(company_id), company_title, now, now),
            )
            if cur.rowcount:
                return True
            conn.execute(
                """
                UPDATE outbox
                SET company_id = ?, contact_name = ?, updated_at = ?
                WHERE email = ? AND status = 'pending'
                """,
                (str(company_id), company_title, now, email),
            )
            return False

    def upsert_contact(self, *, email: str, contact_id: str, contact_name: str) -> bool:
        """Legacy contact insert (kept for compatibility). Prefer upsert_company."""
        now = _utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO outbox
                    (email, company_id, contact_id, contact_name, status, created_at, updated_at)
                VALUES (?, '', ?, ?, 'pending', ?, ?)
                """,
                (email, str(contact_id), contact_name, now, now),
            )
            if cur.rowcount:
                return True
            conn.execute(
                """
                UPDATE outbox
                SET contact_id = ?, contact_name = ?, updated_at = ?
                WHERE email = ? AND status = 'pending'
                """,
                (str(contact_id), contact_name, now, email),
            )
            return False

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM outbox GROUP BY status"
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) AS n FROM outbox").fetchone()["n"]
        out = {r["status"]: int(r["n"]) for r in rows}
        out["total"] = int(total)
        return out

    def list_pending(self, limit: int, *, only_email: str | None = None) -> list[OutboxRow]:
        with self.connect() as conn:
            if only_email:
                rows = conn.execute(
                    """
                    SELECT * FROM outbox
                    WHERE status = 'pending' AND lower(email) = lower(?)
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (only_email.strip(), limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM outbox
                    WHERE status = 'pending'
                    ORDER BY id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
        return [self._row(r) for r in rows]

    def company_already_contacted(self, company_id: str) -> bool:
        cid = (company_id or "").strip()
        if not cid:
            return False
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT 1 FROM outbox
                WHERE company_id = ?
                  AND status IN ('sent', 'sending', 'replied')
                LIMIT 1
                """,
                (cid,),
            ).fetchone()
        return row is not None

    def claim_for_send(self, row_id: int, *, message_id: str) -> bool:
        """Atomically pending → sending with pre-generated Message-ID."""
        now = _utc_now()
        mid = (message_id or "").strip().strip("<>")
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox
                SET status = 'sending',
                    message_id = ?,
                    updated_at = ?,
                    attempts = attempts + 1
                WHERE id = ? AND status = 'pending'
                """,
                (mid, now, row_id),
            )
            return bool(cur.rowcount)

    def mark(
        self,
        row_id: int,
        status: Status,
        *,
        error: str | None = None,
        deal_id: str | int | None = None,
        message_id: str | None = None,
    ) -> None:
        now = _utc_now()
        sent_at = now if status in ("sent", "dry_run") else None
        mid = (message_id or "").strip().strip("<>") or None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status = ?,
                    last_error = ?,
                    sent_at = COALESCE(?, sent_at),
                    deal_id = COALESCE(?, deal_id),
                    message_id = COALESCE(?, message_id),
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    status,
                    error,
                    sent_at,
                    str(deal_id) if deal_id is not None else None,
                    mid,
                    now,
                    row_id,
                ),
            )

    def release_claim(self, row_id: int, *, error: str) -> None:
        """sending → failed after SMTP error (Message-ID kept for reconciliation)."""
        self.mark(row_id, "failed", error=error)

    def cancel(self, row_id: int, *, reason: str = "cancelled") -> None:
        self.set_status(row_id, "cancelled", error=reason)

    def find_by_message_id(self, message_id: str) -> OutboxRow | None:
        mid = (message_id or "").strip().strip("<>").lower()
        if not mid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM outbox
                WHERE lower(message_id) = ?
                ORDER BY id DESC LIMIT 1
                """,
                (mid,),
            ).fetchone()
        return self._row(row) if row else None

    def sent_today_count(self) -> int:
        day = datetime.now(timezone.utc).date().isoformat()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM outbox
                WHERE (
                    status IN ('sent', 'replied')
                    AND sent_at IS NOT NULL AND sent_at LIKE ?
                ) OR (
                    status = 'sending' AND updated_at LIKE ?
                )
                """,
                (f"{day}%", f"{day}%"),
            ).fetchone()
        return int(row["n"])

    def find_by_email(self, email: str) -> OutboxRow | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM outbox
                WHERE lower(email) = lower(?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (email.strip(),),
            ).fetchone()
        return self._row(row) if row else None

    def ensure_manual_recipient(self, *, email: str, contact_name: str) -> OutboxRow:
        """Get or create an outbox row for a one-shot / manual send."""
        existing = self.find_by_email(email)
        if existing:
            return existing
        now = _utc_now()
        name = (contact_name or "тест").strip() or "тест"
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO outbox
                    (email, company_id, contact_id, contact_name, status, created_at, updated_at)
                VALUES (?, '', '', ?, 'pending', ?, ?)
                """,
                (email.strip().lower(), name, now, now),
            )
            row_id = int(cur.lastrowid)
        row = self.get_row(row_id)
        assert row is not None
        return row

    def find_outreach_by_email(self, email: str) -> OutboxRow | None:
        """Find a previously sent (or replied) outreach row by recipient email."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM outbox
                WHERE lower(email) = lower(?)
                  AND status IN ('sent', 'replied')
                ORDER BY id DESC
                LIMIT 1
                """,
                (email.strip(),),
            ).fetchone()
        return self._row(row) if row else None

    def mark_replied(self, row_id: int) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status = 'replied',
                    replied_at = COALESCE(replied_at, ?),
                    updated_at = ?
                WHERE id = ? AND status IN ('sent', 'replied')
                """,
                (now, now, row_id),
            )

    def mark_bounced(self, row_id: int, *, reason: str | None = None) -> None:
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE outbox
                SET status = 'bounced',
                    last_error = COALESCE(?, last_error),
                    updated_at = ?
                WHERE id = ? AND status IN ('sent', 'pending', 'failed', 'bounced', 'sending')
                """,
                ((reason or "bounce")[:500], now, row_id),
            )

    def inbound_seen(self, message_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM inbound_replies WHERE message_id = ?",
                (message_id,),
            ).fetchone()
        return row is not None

    def record_inbound(
        self,
        *,
        message_id: str,
        from_email: str,
        subject: str,
        outbox_id: int | None,
        deal_id: str | None,
        notified: bool,
    ) -> bool:
        """Insert inbound Message-ID. Returns False if already known."""
        now = _utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO inbound_replies
                    (message_id, from_email, subject, outbox_id, deal_id, notified, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    from_email,
                    subject,
                    outbox_id,
                    deal_id,
                    1 if notified else 0,
                    now,
                ),
            )
            return bool(cur.rowcount)

    def _row(self, r: sqlite3.Row) -> OutboxRow:
        keys = set(r.keys())
        return OutboxRow(
            id=int(r["id"]),
            email=str(r["email"]),
            company_id=str(r["company_id"] if "company_id" in keys else "") or "",
            contact_id=str(r["contact_id"]),
            contact_name=str(r["contact_name"]),
            status=str(r["status"]),
            attempts=int(r["attempts"]),
            last_error=r["last_error"],
            sent_at=r["sent_at"],
            deal_id=str(r["deal_id"]) if "deal_id" in keys and r["deal_id"] else None,
            message_id=str(r["message_id"]) if "message_id" in keys and r["message_id"] else None,
            created_at=str(r["created_at"]),
            updated_at=str(r["updated_at"]),
        )

    def status_report(self) -> dict[str, Any]:
        with self.connect() as conn:
            inbound = conn.execute("SELECT COUNT(*) AS n FROM inbound_replies").fetchone()[
                "n"
            ]
        return {
            "db_path": str(self.db_path),
            "counts": self.counts(),
            "sent_today": self.sent_today_count(),
            "inbound_replies": int(inbound),
        }

    def list_outbox(
        self,
        *,
        status: str | None = None,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[OutboxRow], int]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if q:
            clauses.append(
                "(lower(email) LIKE ? OR lower(contact_name) LIKE ? OR company_id LIKE ?)"
            )
            like = f"%{q.strip().lower()}%"
            params.extend([like, like, f"%{q.strip()}%"])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM outbox{where}", params
            ).fetchone()["n"]
            rows = conn.execute(
                f"""
                SELECT * FROM outbox{where}
                ORDER BY updated_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return [self._row(r) for r in rows], int(total)

    def get_row(self, row_id: int) -> OutboxRow | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM outbox WHERE id = ?", (row_id,)
            ).fetchone()
        return self._row(row) if row else None

    def set_status(self, row_id: int, status: Status, *, error: str | None = None) -> bool:
        now = _utc_now()
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE outbox
                SET status = ?, last_error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error, now, row_id),
            )
            return bool(cur.rowcount)

    def stats_daily(self, days: int = 14) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT substr(sent_at, 1, 10) AS day,
                       SUM(CASE WHEN status IN ('sent','replied') THEN 1 ELSE 0 END) AS sent,
                       SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) AS replied,
                       SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed
                FROM outbox
                WHERE sent_at IS NOT NULL
                  AND sent_at >= date('now', ?)
                GROUP BY day
                ORDER BY day ASC
                """,
                (f"-{max(1, days)} day",),
            ).fetchall()
        return [
            {
                "day": r["day"],
                "sent": int(r["sent"] or 0),
                "replied": int(r["replied"] or 0),
                "failed": int(r["failed"] or 0),
            }
            for r in rows
        ]

    def list_inbound(self, *, limit: int = 50, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM inbound_replies").fetchone()["n"]
            rows = conn.execute(
                """
                SELECT * FROM inbound_replies
                ORDER BY id DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        items = []
        for r in rows:
            items.append(
                {
                    "id": int(r["id"]),
                    "message_id": r["message_id"],
                    "from_email": r["from_email"],
                    "subject": r["subject"],
                    "outbox_id": r["outbox_id"],
                    "deal_id": r["deal_id"],
                    "notified": bool(r["notified"]),
                    "created_at": r["created_at"],
                }
            )
        return items, int(total)
