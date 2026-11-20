from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "data" / "list_mailer.db"
ALLOWED_FROM = "rdv@quantumlabs.ru"
BLOCKED_FROM = frozenset({"office@quantumlabs.ru"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _today() -> str:
    return date.today().isoformat()


@dataclass
class Recipient:
    id: int
    campaign_id: int
    email: str
    company: str
    priority: str
    subject: str
    plain_path: str
    html_path: str
    status: str
    message_id: str
    sent_at: str
    error: str
    meta_json: str


class Store:
    """SQLite queue for list campaigns — isolated from ava-outreach outbox.db."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("LIST_MAILER_DB", str(DEFAULT_DB)))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS campaigns (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  slug TEXT NOT NULL UNIQUE,
                  title TEXT NOT NULL,
                  from_email TEXT NOT NULL,
                  created_at TEXT NOT NULL,
                  notes TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS recipients (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  campaign_id INTEGER NOT NULL REFERENCES campaigns(id),
                  email TEXT NOT NULL,
                  company TEXT DEFAULT '',
                  priority TEXT DEFAULT '',
                  subject TEXT NOT NULL,
                  plain_path TEXT NOT NULL,
                  html_path TEXT DEFAULT '',
                  status TEXT NOT NULL DEFAULT 'pending',
                  message_id TEXT DEFAULT '',
                  sent_at TEXT DEFAULT '',
                  error TEXT DEFAULT '',
                  meta_json TEXT DEFAULT '{}',
                  UNIQUE(campaign_id, email)
                );
                CREATE TABLE IF NOT EXISTS daily_sends (
                  day TEXT PRIMARY KEY,
                  count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_recipients_status
                  ON recipients(campaign_id, status);
                """
            )

    def upsert_campaign(
        self, *, slug: str, title: str, from_email: str = ALLOWED_FROM, notes: str = ""
    ) -> int:
        if from_email.lower() in BLOCKED_FROM or from_email.lower() != ALLOWED_FROM:
            raise ValueError(f"from_email must be {ALLOWED_FROM}, got {from_email}")
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO campaigns(slug, title, from_email, created_at, notes)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(slug) DO UPDATE SET
                  title=excluded.title,
                  notes=excluded.notes
                """,
                (slug, title, from_email, _utc_now(), notes),
            )
            row = c.execute("SELECT id FROM campaigns WHERE slug = ?", (slug,)).fetchone()
            return int(row["id"])

    def get_campaign(self, slug: str) -> sqlite3.Row | None:
        with self._conn() as c:
            return c.execute("SELECT * FROM campaigns WHERE slug = ?", (slug,)).fetchone()

    def list_campaigns(self) -> list[sqlite3.Row]:
        with self._conn() as c:
            return list(c.execute("SELECT * FROM campaigns ORDER BY id"))

    def add_recipient(
        self,
        *,
        campaign_id: int,
        email: str,
        company: str,
        priority: str,
        subject: str,
        plain_path: str,
        html_path: str = "",
        meta_json: str = "{}",
        reset_if_pending: bool = True,
    ) -> int:
        email_n = email.strip().lower()
        with self._conn() as c:
            existing = c.execute(
                "SELECT id, status FROM recipients WHERE campaign_id=? AND email=?",
                (campaign_id, email_n),
            ).fetchone()
            if existing:
                if existing["status"] == "sent":
                    return int(existing["id"])
                if reset_if_pending:
                    c.execute(
                        """
                        UPDATE recipients SET company=?, priority=?, subject=?,
                          plain_path=?, html_path=?, meta_json=?, status='pending',
                          error='', message_id='', sent_at=''
                        WHERE id=?
                        """,
                        (
                            company,
                            priority,
                            subject,
                            plain_path,
                            html_path,
                            meta_json,
                            existing["id"],
                        ),
                    )
                return int(existing["id"])
            cur = c.execute(
                """
                INSERT INTO recipients(
                  campaign_id, email, company, priority, subject,
                  plain_path, html_path, status, meta_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                """,
                (
                    campaign_id,
                    email_n,
                    company,
                    priority,
                    subject,
                    plain_path,
                    html_path,
                    meta_json,
                ),
            )
            return int(cur.lastrowid)

    def pending(
        self, *, campaign_id: int | None = None, priority: str | None = None, limit: int = 50
    ) -> list[Recipient]:
        q = "SELECT * FROM recipients WHERE status = 'pending'"
        args: list[object] = []
        if campaign_id is not None:
            q += " AND campaign_id = ?"
            args.append(campaign_id)
        if priority and priority.upper() != "ALL":
            q += " AND UPPER(priority) = ?"
            args.append(priority.upper())
        q += " ORDER BY id LIMIT ?"
        args.append(limit)
        with self._conn() as c:
            rows = c.execute(q, args).fetchall()
        return [Recipient(**dict(r)) for r in rows]

    def mark_sent(self, recipient_id: int, message_id: str) -> None:
        with self._conn() as c:
            c.execute(
                """
                UPDATE recipients
                SET status='sent', message_id=?, sent_at=?, error=''
                WHERE id=?
                """,
                (message_id, _utc_now(), recipient_id),
            )

    def mark_failed(self, recipient_id: int, error: str) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE recipients SET status='failed', error=? WHERE id=?",
                (error[:500], recipient_id),
            )

    def sent_today(self) -> int:
        with self._conn() as c:
            row = c.execute(
                "SELECT count FROM daily_sends WHERE day = ?", (_today(),)
            ).fetchone()
            return int(row["count"]) if row else 0

    def bump_sent_today(self) -> int:
        with self._conn() as c:
            c.execute(
                """
                INSERT INTO daily_sends(day, count) VALUES (?, 1)
                ON CONFLICT(day) DO UPDATE SET count = count + 1
                """,
                (_today(),),
            )
            row = c.execute(
                "SELECT count FROM daily_sends WHERE day = ?", (_today(),)
            ).fetchone()
            return int(row["count"])

    def stats(self, campaign_id: int | None = None) -> dict:
        with self._conn() as c:
            if campaign_id is None:
                rows = c.execute(
                    "SELECT status, COUNT(*) AS n FROM recipients GROUP BY status"
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT status, COUNT(*) AS n FROM recipients WHERE campaign_id=? GROUP BY status",
                    (campaign_id,),
                ).fetchall()
        out = {r["status"]: int(r["n"]) for r in rows}
        out["sent_today"] = self.sent_today()
        return out
