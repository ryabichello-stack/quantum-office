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
from content.packs import get_pack, list_packs

logger = logging.getLogger("ava-outreach.sequences")

# Absolute offsets from first send (day 0) — used when no industry pack selected
DEFAULT_STEPS: list[dict[str, Any]] = [
    {
        "step": 1,
        "delay_days": 0,
        "subject": None,  # use campaign subject
        "plain": None,  # use campaign template
        "html": None,
        "label": "intro",
        "attach_presentation": False,
    },
    {
        "step": 2,
        "delay_days": 3,
        "subject": "Re: {subject}",
        "plain": (
            "Добрый день, {name}!\n\n"
            "Подскажите, пожалуйста, успели посмотреть моё письмо ниже?\n\n"
            "Если тема массовых выплат / платёжных сценариев не актуальна — "
            "просто ответьте «неинтересно», больше писать не буду.\n\n"
            "С уважением,\n{company}\n"
        ),
        "html": None,
        "label": "bump",
        "attach_presentation": False,
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
        "html": None,
        "label": "route",
        "attach_presentation": False,
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

    def steps(self, pack_id: str | None = None) -> list[dict[str, Any]]:
        from content.pack_drafts import PackDraftStore, resolve_pack
        from core.paths import SETTINGS_DB

        pack = (
            resolve_pack(pack_id or "", PackDraftStore(SETTINGS_DB))
            if pack_id
            else None
        )
        if pack and pack.get("steps"):
            return list(pack["steps"])
        return list(DEFAULT_STEPS)

    def max_step(self, pack_id: str | None = None) -> int:
        steps = self.steps(pack_id)
        return max(int(s["step"]) for s in steps)

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
        pack_id: str = "",
        meta: dict[str, Any] | None = None,
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
        meta_obj: dict[str, Any] = dict(meta or {})
        pid = (pack_id or "").strip() or str(meta_obj.get("pack_id") or "")
        if pid:
            meta_obj["pack_id"] = pid
        meta_json = json.dumps(meta_obj, ensure_ascii=False)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO sequence_leads(
                    email, company_id, contact_name, current_step, status,
                    next_action_at, last_outbox_id, subject_base, meta_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, 0, 'active', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                    company_id=excluded.company_id,
                    contact_name=excluded.contact_name,
                    status='active',
                    stop_reason=NULL,
                    current_step=0,
                    next_action_at=excluded.next_action_at,
                    last_outbox_id=COALESCE(excluded.last_outbox_id, sequence_leads.last_outbox_id),
                    subject_base=COALESCE(excluded.subject_base, sequence_leads.subject_base),
                    meta_json=excluded.meta_json,
                    updated_at=excluded.updated_at
                """,
                (
                    em,
                    (company_id or "").strip(),
                    (contact_name or "").strip(),
                    now,  # due immediately for step 1
                    outbox_id,
                    subject_base or "",
                    meta_json,
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

    def _pack_id_of(self, lead: dict[str, Any]) -> str:
        try:
            meta = json.loads(lead.get("meta_json") or "{}")
        except Exception:
            meta = {}
        if isinstance(meta, dict):
            return str(meta.get("pack_id") or "").strip()
        return ""

    def mark_step_sent(
        self,
        lead_id: int,
        *,
        step: int,
        outbox_id: int | None,
        subject_base: str | None = None,
        timezone_name: str | None = None,
        settings: Any = None,
    ) -> dict[str, Any] | None:
        lead = self.get(lead_id)
        if not lead:
            return None
        now = _utc_now()
        pack_id = self._pack_id_of(lead)
        steps = self.steps(pack_id)
        max_s = self.max_step(pack_id)
        try:
            meta = json.loads(lead.get("meta_json") or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except Exception:  # noqa: BLE001
            meta = {}

        if step == 1 or not meta.get("anchor_sent_at"):
            meta["anchor_sent_at"] = _iso(now)
        if timezone_name:
            meta["timezone"] = str(timezone_name).strip()
        tz_name = str(meta.get("timezone") or timezone_name or "").strip() or None

        if step >= max_s:
            status = "completed"
            next_at = None
            stop_reason = "sequence_completed_no_reply"
        else:
            status = "active"
            next_step = next(s for s in steps if int(s["step"]) == step + 1)
            delay_abs = int(next_step.get("delay_days") or 0)
            try:
                from geo_schedule import snap_followup_utc

                anchor = datetime.fromisoformat(
                    str(meta["anchor_sent_at"]).replace("Z", "+00:00")
                )
                if anchor.tzinfo is None:
                    anchor = anchor.replace(tzinfo=timezone.utc)
                next_dt = snap_followup_utc(
                    anchor,
                    delay_days=delay_abs,
                    tz_name=tz_name,
                    settings=settings,
                    now_utc=now,
                )
                next_at = _iso(next_dt)
            except Exception:  # noqa: BLE001
                logger.exception("snap follow-up failed; fallback gap days")
                prev = next(s for s in steps if int(s["step"]) == step)
                gap = int(next_step["delay_days"]) - int(prev["delay_days"])
                next_at = _iso(now + timedelta(days=max(0, gap)))
            stop_reason = None
        meta_json = json.dumps(meta, ensure_ascii=False)
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
                    meta_json=?,
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
                    meta_json,
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
                ORDER BY next_action_at ASC
                LIMIT ?
                """,
                (now, max(1, limit)),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            pack_id = self._pack_id_of(d)
            if int(d.get("current_step") or 0) >= self.max_step(pack_id):
                continue
            d["pack_id"] = pack_id
            d["step_def"] = self.next_step_def(d)
            out.append(d)
        return out

    def next_step_def(self, lead: dict[str, Any]) -> dict[str, Any] | None:
        nxt = int(lead.get("current_step") or 0) + 1
        for s in self.steps(self._pack_id_of(lead)):
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
    version = "1.1.0"

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
        return {
            "ok": True,
            "counts": self.store.counts(),
            "steps": len(DEFAULT_STEPS),
            "packs": [p["id"] for p in list_packs()],
        }

    def register_routes(self, router: Any) -> None:
        from pydantic import BaseModel

        @router.get("/status")
        def status() -> dict[str, Any]:
            return {
                "ok": True,
                "counts": self.store.counts(),
                "steps": DEFAULT_STEPS,
                "packs": list_packs(),
                "due": self.store.list_due(10),
            }

        @router.get("/packs")
        def packs() -> dict[str, Any]:
            return {"ok": True, "items": list_packs()}

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
