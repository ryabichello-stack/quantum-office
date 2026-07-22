"""Multi-step email sequences (lean: 3 steps, no visual builder)."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.sequences")

# Absolute offsets from first send (day 0)
DEFAULT_STEPS: list[dict[str, Any]] = [
    {
        "step": 1,
        "delay_days": 0,
        "subject": None,  # use campaign subject
        "plain": None,  # use campaign template
        "label": "intro",
    },
    {
        "step": 2,
        "delay_days": 3,
        "subject": "Re: {subject}",
        "plain": (
            "Добрый день, {name}!\n\n"
            "Подскажите, пожалуйста, успели посмотреть моё письмо ниже?\n\n"
            "Если тема автоматизации выплат / AI-секретаря не актуальна — "
            "просто ответьте «неинтересно», больше писать не буду.\n\n"
            "С уважением,\n{company}\n"
        ),
        "label": "bump",
    },
    {
        "step": 3,
        "delay_days": 7,
        "subject": "Re: {subject}",
        "plain": (
            "Добрый день, {name}!\n\n"
            "Возможно, вопрос находится в зоне ответственности другого коллеги. "
            "Подскажите, кому корректнее направить краткое описание?\n\n"
            "Если не актуально — напишите, и я закрою тему.\n\n"
            "С уважением,\n{company}\n"
        ),
        "label": "route",
    },
]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class SequenceStore:
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
                CREATE TABLE IF NOT EXISTS sequence_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL UNIQUE,
                    company_id TEXT NOT NULL DEFAULT '',
                    contact_name TEXT NOT NULL DEFAULT '',
                    current_step INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'active',
                    stop_reason TEXT,
                    next_action_at TEXT,
                    last_outbox_id INTEGER,
                    subject_base TEXT,
                    meta_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_seq_due "
                "ON sequence_leads(status, next_action_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_seq_company ON sequence_leads(company_id)"
            )

    def steps(self) -> list[dict[str, Any]]:
        return list(DEFAULT_STEPS)

    def max_step(self) -> int:
        return max(int(s["step"]) for s in DEFAULT_STEPS)

    def get_by_email(self, email: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sequence_leads WHERE lower(email) = lower(?)",
                ((email or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def get(self, lead_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sequence_leads WHERE id = ?", (lead_id,)
            ).fetchone()
        return dict(row) if row else None

    def enroll(
        self,
        *,
        email: str,
        company_id: str = "",
        contact_name: str = "",
        subject_base: str = "",
        outbox_id: int | None = None,
    ) -> dict[str, Any]:
        em = (email or "").strip().lower()
        now = _iso(_utc_now())
        existing = self.get_by_email(em)
        if existing:
            if existing.get("status") == "active":
                return existing
            # re-enroll only if stopped/completed and not do-not-contact reason
            if existing.get("stop_reason") in (
                "unsubscribe",
                "negative",
                "hard_bounce",
                "call_refused",
            ):
                return existing
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sequence_leads(
                    email, company_id, contact_name, current_step, status,
                    next_action_at, last_outbox_id, subject_base, meta_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 0, 'active', ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    company_id=excluded.company_id,
                    contact_name=excluded.contact_name,
                    status='active',
                    stop_reason=NULL,
                    current_step=0,
                    next_action_at=excluded.next_action_at,
                    last_outbox_id=COALESCE(excluded.last_outbox_id, sequence_leads.last_outbox_id),
                    subject_base=COALESCE(excluded.subject_base, sequence_leads.subject_base),
                    updated_at=excluded.updated_at
                """,
                (
                    em,
                    (company_id or "").strip(),
                    (contact_name or "").strip(),
                    now,  # due immediately for step 1
                    outbox_id,
                    subject_base or "",
                    now,
                    now,
                ),
            )
        return self.get_by_email(em) or {}

    def stop(
        self,
        *,
        email: str | None = None,
        company_id: str | None = None,
        reason: str,
    ) -> int:
        now = _iso(_utc_now())
        with self.connect() as conn:
            if email:
                cur = conn.execute(
                    """
                    UPDATE sequence_leads
                    SET status='stopped', stop_reason=?, next_action_at=NULL, updated_at=?
                    WHERE lower(email)=lower(?) AND status='active'
                    """,
                    (reason, now, email.strip()),
                )
                return int(cur.rowcount)
            if company_id:
                cur = conn.execute(
                    """
                    UPDATE sequence_leads
                    SET status='stopped', stop_reason=?, next_action_at=NULL, updated_at=?
                    WHERE company_id=? AND status='active'
                    """,
                    (reason, now, company_id.strip()),
                )
                return int(cur.rowcount)
        return 0

    def mark_step_sent(
        self,
        lead_id: int,
        *,
        step: int,
        outbox_id: int | None,
        subject_base: str | None = None,
    ) -> dict[str, Any] | None:
        lead = self.get(lead_id)
        if not lead:
            return None
        now = _utc_now()
        max_s = self.max_step()
        if step >= max_s:
            status = "completed"
            next_at = None
            stop_reason = "sequence_completed_no_reply"
        else:
            status = "active"
            # next step absolute offset from first send: find next step delay_days
            next_step = next(s for s in DEFAULT_STEPS if int(s["step"]) == step + 1)
            # schedule relative to now for simplicity (delay between steps)
            prev = next(s for s in DEFAULT_STEPS if int(s["step"]) == step)
            gap = int(next_step["delay_days"]) - int(prev["delay_days"])
            next_at = _iso(now + timedelta(days=max(0, gap)))
            stop_reason = None
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sequence_leads
                SET current_step=?,
                    status=?,
                    stop_reason=COALESCE(?, stop_reason),
                    next_action_at=?,
                    last_outbox_id=COALESCE(?, last_outbox_id),
                    subject_base=COALESCE(?, subject_base),
                    updated_at=?
                WHERE id=?
                """,
                (
                    step,
                    status,
                    stop_reason,
                    next_at,
                    outbox_id,
                    subject_base,
                    _iso(now),
                    lead_id,
                ),
            )
        return self.get(lead_id)

    def list_due(self, limit: int = 20) -> list[dict[str, Any]]:
        now = _iso(_utc_now())
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sequence_leads
                WHERE status='active'
                  AND next_action_at IS NOT NULL
                  AND next_action_at <= ?
                  AND current_step < ?
                ORDER BY next_action_at ASC
                LIMIT ?
                """,
                (now, self.max_step(), max(1, limit)),
            ).fetchall()
        return [dict(r) for r in rows]

    def next_step_def(self, lead: dict[str, Any]) -> dict[str, Any] | None:
        nxt = int(lead.get("current_step") or 0) + 1
        for s in DEFAULT_STEPS:
            if int(s["step"]) == nxt:
                return s
        return None

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM sequence_leads GROUP BY status"
            ).fetchall()
        out = {str(r["status"]): int(r["n"]) for r in rows}
        out["total"] = sum(out.values())
        return out

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sequence_leads
                ORDER BY updated_at DESC LIMIT ?
                """,
                (max(1, min(limit, 200)),),
            ).fetchall()
        return [dict(r) for r in rows]


class SequencesModule:
    name = "sequences"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = SequenceStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["sequences"] = self.store
        logger.info("sequences module ready %s", self.store.counts())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "counts": self.store.counts(), "steps": len(DEFAULT_STEPS)}

    def register_routes(self, router: Any) -> None:
        from pydantic import BaseModel

        @router.get("/status")
        def status() -> dict[str, Any]:
            return {
                "ok": True,
                "counts": self.store.counts(),
                "steps": DEFAULT_STEPS,
                "due": self.store.list_due(10),
            }

        @router.get("/leads")
        def leads(limit: int = 50) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_recent(limit)}

        class StopBody(BaseModel):
            email: str | None = None
            company_id: str | None = None
            reason: str = "manual"

        @router.post("/stop")
        def stop(body: StopBody) -> dict[str, Any]:
            n = self.store.stop(
                email=body.email, company_id=body.company_id, reason=body.reason
            )
            return {"ok": True, "stopped": n}
