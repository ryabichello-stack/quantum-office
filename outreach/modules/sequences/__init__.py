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
            if existing.get("status") in ("active", "paused"):
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
                    WHERE lower(email)=lower(?) AND status IN ('active', 'paused')
                    """,
                    (reason, now, email.strip()),
                )
                return int(cur.rowcount)
            if company_id:
                cur = conn.execute(
                    """
                    UPDATE sequence_leads
                    SET status='stopped', stop_reason=?, next_action_at=NULL, updated_at=?
                    WHERE company_id=? AND status IN ('active', 'paused')
                    """,
                    (reason, now, company_id.strip()),
                )
                return int(cur.rowcount)
        return 0

    def pause(
        self,
        *,
        email: str | None = None,
        company_id: str | None = None,
        reason: str = "out_of_office",
        days: int = 7,
        settings: Any = None,
    ) -> int:
        """Pause active sequence until local B2B window after ``days`` calendar days."""
        from geo_schedule import next_send_datetime

        pause_days = max(1, min(int(days or 7), 60))
        until = next_send_datetime(
            _utc_now() + timedelta(days=pause_days),
            None,
            settings=settings,
            prefer_preferred_days=True,
        )
        until_iso = _iso(until)
        now = _iso(_utc_now())
        with self.connect() as conn:
            if email:
                rows = conn.execute(
                    """
                    SELECT id, meta_json FROM sequence_leads
                    WHERE lower(email)=lower(?) AND status IN ('active', 'paused')
                    """,
                    (email.strip(),),
                ).fetchall()
            elif company_id:
                rows = conn.execute(
                    """
                    SELECT id, meta_json FROM sequence_leads
                    WHERE company_id=? AND status IN ('active', 'paused')
                    """,
                    (company_id.strip(),),
                ).fetchall()
            else:
                return 0
            n = 0
            for r in rows:
                try:
                    meta = json.loads(r["meta_json"] or "{}")
                    if not isinstance(meta, dict):
                        meta = {}
                except Exception:  # noqa: BLE001
                    meta = {}
                meta["paused_until"] = until_iso
                meta["pause_reason"] = reason
                conn.execute(
                    """
                    UPDATE sequence_leads
                    SET status='paused', stop_reason=?, next_action_at=?,
                        meta_json=?, updated_at=?
                    WHERE id=?
                    """,
                    (
                        reason,
                        until_iso,
                        json.dumps(meta, ensure_ascii=False),
                        now,
                        r["id"],
                    ),
                )
                n += 1
            return n

    def resume_due_pauses(self) -> int:
        """Flip paused leads whose next_action_at has passed back to active."""
        now = _iso(_utc_now())
        with self.connect() as conn:
            cur = conn.execute(
                """
                UPDATE sequence_leads
                SET status='active', stop_reason=NULL, updated_at=?
                WHERE status='paused'
                  AND next_action_at IS NOT NULL
                  AND next_action_at <= ?
                """,
                (now, now),
            )
            return int(cur.rowcount)

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
        self.resume_due_pauses()
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

    def list_upcoming(self, limit: int = 50) -> list[dict[str, Any]]:
        """Active leads with a future next_action_at (not yet due)."""
        now = _iso(_utc_now())
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM sequence_leads
                WHERE status='active'
                  AND next_action_at IS NOT NULL
                  AND next_action_at > ?
                ORDER BY next_action_at ASC
                LIMIT ?
                """,
                (now, max(1, min(limit, 200))),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            pack_id = self._pack_id_of(d)
            d["pack_id"] = pack_id
            d["step_def"] = self.next_step_def(d)
            out.append(d)
        return out

    def list_scheduled_until(self, until_iso: str, *, limit: int = 1000) -> list[dict[str, Any]]:
        """Active leads with next_action_at on or before ``until_iso`` (due + upcoming)."""
        self.resume_due_pauses()
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
                (until_iso, max(1, min(int(limit), 2000))),
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

    def _lead_queue_row(self, lead: dict[str, Any], *, due: bool) -> dict[str, Any]:
        step_def = lead.get("step_def") or self.next_step_def(lead) or {}
        meta: dict[str, Any] = {}
        try:
            meta = json.loads(lead.get("meta_json") or "{}")
            if not isinstance(meta, dict):
                meta = {}
        except Exception:  # noqa: BLE001
            meta = {}
        nxt = int(step_def.get("step") or (int(lead.get("current_step") or 0) + 1))
        return {
            "kind": "followup",
            "email": lead.get("email"),
            "company_id": lead.get("company_id") or "",
            "contact_name": lead.get("contact_name") or "",
            "current_step": int(lead.get("current_step") or 0),
            "next_step": nxt,
            "next_label": step_def.get("label") or f"step_{nxt}",
            "next_subject": step_def.get("subject") or lead.get("subject_base") or "",
            "delay_days": step_def.get("delay_days"),
            "next_action_at": lead.get("next_action_at"),
            "due": due,
            "pack_id": lead.get("pack_id") or meta.get("pack_id") or "",
            "timezone": meta.get("timezone") or "",
            "anchor_sent_at": meta.get("anchor_sent_at") or "",
        }

    def calendar_snapshot(
        self,
        *,
        days: int = 14,
        first_touch: list[dict[str, Any]] | None = None,
        limit: int = 1000,
    ) -> dict[str, Any]:
        """14-day (default) operator calendar: follow-ups + first-touch by Moscow date."""
        from zoneinfo import ZoneInfo

        days_n = max(1, min(int(days or 14), 60))
        msk = ZoneInfo("Europe/Moscow")
        today = datetime.now(msk).date()
        end = today + timedelta(days=days_n - 1)
        until_local = datetime(
            end.year, end.month, end.day, 23, 59, 59, tzinfo=msk
        )
        until_iso = _iso(until_local.astimezone(timezone.utc))
        now_iso = _iso(_utc_now())

        buckets: dict[str, list[dict[str, Any]]] = {
            (today + timedelta(days=i)).isoformat(): [] for i in range(days_n)
        }

        def _day_key(iso: str | None) -> str:
            if not iso:
                return today.isoformat()
            try:
                raw = str(iso).replace("Z", "+00:00")
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                local_d = dt.astimezone(msk).date()
                if local_d < today:
                    return today.isoformat()
                return local_d.isoformat()
            except Exception:  # noqa: BLE001
                return today.isoformat()

        for lead in self.list_scheduled_until(until_iso, limit=limit):
            due = bool(lead.get("next_action_at") and str(lead["next_action_at"]) <= now_iso)
            row = self._lead_queue_row(lead, due=due)
            key = _day_key(row.get("next_action_at"))
            if key in buckets:
                buckets[key].append(row)

        for item in first_touch or []:
            key = _day_key(item.get("next_slot_at") or item.get("next_action_at"))
            if key in buckets:
                buckets[key].append(item)

        day_rows: list[dict[str, Any]] = []
        total_items = 0
        total_due = 0
        for day, items in buckets.items():
            due_n = sum(1 for x in items if x.get("due"))
            total_items += len(items)
            total_due += due_n
            preview_limit = 8
            day_rows.append(
                {
                    "date": day,
                    "count": len(items),
                    "due_count": due_n,
                    "items": items[:preview_limit],
                    "truncated": len(items) > preview_limit,
                }
            )

        return {
            "ok": True,
            "days": days_n,
            "timezone": "Europe/Moscow",
            "from": today.isoformat(),
            "to": end.isoformat(),
            "totals": {
                "items": total_items,
                "due": total_due,
                "days_with_items": sum(1 for d in day_rows if d["count"]),
            },
            "calendar": day_rows,
        }

    def queue_snapshot(
        self,
        *,
        first_touch: list[dict[str, Any]] | None = None,
        due_limit: int = 40,
        upcoming_limit: int = 40,
    ) -> dict[str, Any]:
        """Unified view: first letters vs chain follow-ups."""
        due_raw = self.list_due(limit=due_limit)
        upcoming_raw = self.list_upcoming(limit=upcoming_limit)
        counts = self.counts()

        followups_due = [self._lead_queue_row(x, due=True) for x in due_raw]
        followups_upcoming = [self._lead_queue_row(x, due=False) for x in upcoming_raw]
        return {
            "ok": True,
            "send_order": "followups_due_then_first_touch",
            "send_order_ru": (
                "В каждой пачке сначала уходят письма цепочки, у которых подошёл срок "
                "(шаг 2, 3… по дате первого письма и локальному окну). "
                "Оставшийся дневной лимит — на новые первые письма из очереди. "
                "У каждого контакта своя цепочка: сегодня одному шаг 1, другому шаг 2."
            ),
            "counts": {
                "first_touch_pending": len(first_touch or []),
                "followups_due": len(followups_due),
                "followups_upcoming": len(followups_upcoming),
                "sequences": counts,
            },
            "first_touch": first_touch or [],
            "followups_due": followups_due,
            "followups_upcoming": followups_upcoming,
        }

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

        @router.get("/queue")
        def queue(limit: int = 40) -> dict[str, Any]:
            """First-touch pending + due/upcoming follow-ups for the Очередь UI."""
            from modules.clients import ClientsStore, company_geo_row
            from outbox import OutboxStore
            from core.paths import DATA_DIR

            limit_n = max(1, min(int(limit or 40), 100))
            outbox = OutboxStore(DATA_DIR / "outbox.db")
            clients = ClientsStore()
            pending_rows = outbox.list_pending(limit_n)
            first_touch: list[dict[str, Any]] = []
            for row in pending_rows:
                geo = company_geo_row(clients, row.company_id or "")
                first_touch.append(
                    {
                        "kind": "first_touch",
                        "outbox_id": row.id,
                        "email": row.email,
                        "company_id": row.company_id or "",
                        "contact_name": row.contact_name or "",
                        "next_step": 1,
                        "next_label": "intro",
                        "next_subject": "",
                        "timezone": geo.get("timezone") or "",
                        "city": geo.get("city") or "",
                        "director_greeting": geo.get("director_greeting") or "",
                        "due": True,
                    }
                )
            snap = self.store.queue_snapshot(
                first_touch=first_touch,
                due_limit=limit_n,
                upcoming_limit=limit_n,
            )
            # Enrich follow-ups with geo + window status
            from geo_schedule import window_status
            from core.paths import SETTINGS_DB
            from runtime_settings import RuntimeSettings

            rt = RuntimeSettings(SETTINGS_DB)
            for bucket in ("followups_due", "followups_upcoming"):
                for item in snap.get(bucket) or []:
                    if not item.get("timezone"):
                        geo = company_geo_row(clients, str(item.get("company_id") or ""))
                        item["timezone"] = geo.get("timezone") or ""
                        item["city"] = geo.get("city") or ""
                        if not item.get("contact_name") and geo.get("director_greeting"):
                            item["contact_name"] = geo["director_greeting"]
                    win = window_status(item.get("timezone") or "", settings=rt)
                    item["in_window"] = bool(win.get("in_window"))
                    item["window_label"] = win.get("label") or ""
                    item["next_slot_at"] = win.get("next_slot_at")
                    item["next_slot_local"] = win.get("next_slot_local")
            for item in first_touch:
                win = window_status(item.get("timezone") or "", settings=rt)
                item["in_window"] = bool(win.get("in_window"))
                item["window_label"] = win.get("label") or ""
                item["next_slot_at"] = win.get("next_slot_at")
                item["next_slot_local"] = win.get("next_slot_local")
            # pending total (not just page)
            try:
                pending_total = int(outbox.counts().get("pending") or 0)
            except Exception:  # noqa: BLE001
                pending_total = len(first_touch)
            snap["counts"]["first_touch_pending_total"] = pending_total
            snap["counts"]["first_touch_in_window"] = sum(
                1 for x in first_touch if x.get("in_window")
            )
            return snap

        @router.get("/calendar")
        def calendar(days: int = 14) -> dict[str, Any]:
            """Server-side 14-day queue calendar (Moscow dates)."""
            from modules.clients import ClientsStore, company_geo_row
            from modules.deliverability import DeliverabilityStore
            from modules.sequences.pace import first_touch_daily_cap
            from outbox import OutboxStore
            from core.paths import DATA_DIR, SETTINGS_DB
            from geo_schedule import window_status
            from runtime_settings import RuntimeSettings

            days_n = max(1, min(int(days or 14), 60))
            outbox = OutboxStore(DATA_DIR / "outbox.db")
            clients = ClientsStore()
            rt = RuntimeSettings(SETTINGS_DB)
            deliver = DeliverabilityStore()
            configured = rt.get_int("OUTREACH_DAILY_LIMIT", 15)
            effective = deliver.effective_daily_limit(rt, configured)
            ft_cap = first_touch_daily_cap(rt, effective_daily_limit=effective)
            # Include paced future rows so calendar shows spread, not one giant day
            pending_rows = outbox.list_pending_all(min(2000, 80 * days_n))
            first_touch: list[dict[str, Any]] = []
            for row in pending_rows:
                geo = company_geo_row(clients, row.company_id or "")
                item: dict[str, Any] = {
                    "kind": "first_touch",
                    "outbox_id": row.id,
                    "email": row.email,
                    "company_id": row.company_id or "",
                    "contact_name": row.contact_name or "",
                    "next_step": 1,
                    "next_label": "intro",
                    "next_subject": "",
                    "timezone": geo.get("timezone") or "",
                    "city": geo.get("city") or "",
                    "due": True,
                    "not_before": row.not_before or "",
                }
                win = window_status(item.get("timezone") or "", settings=rt)
                item["in_window"] = bool(win.get("in_window"))
                item["window_label"] = win.get("label") or ""
                # Prefer pacing hold over nearest window so calendar matches send plan
                if row.not_before:
                    item["next_slot_at"] = row.not_before
                    item["next_slot_local"] = row.not_before
                    item["paced"] = True
                else:
                    item["next_slot_at"] = win.get("next_slot_at")
                    item["next_slot_local"] = win.get("next_slot_local")
                    item["paced"] = False
                first_touch.append(item)

            snap = self.store.calendar_snapshot(
                days=days_n, first_touch=first_touch, limit=1000
            )
            for day in snap.get("calendar") or []:
                for item in day.get("items") or []:
                    if item.get("kind") != "followup":
                        continue
                    if not item.get("timezone"):
                        geo = company_geo_row(clients, str(item.get("company_id") or ""))
                        item["timezone"] = geo.get("timezone") or ""
                        item["city"] = geo.get("city") or ""
                day_count = int(day.get("count") or 0)
                day["capacity"] = effective
                day["first_touch_cap"] = ft_cap
                day["over_capacity"] = day_count > effective
                day["spam_risk"] = day_count > max(effective * 2, 20)

            snap["deliverability"] = {
                "configured_daily_limit": configured,
                "effective_daily_limit": effective,
                "first_touch_daily_cap": ft_cap,
                "sent_today": outbox.sent_today_count(),
                "warmup_day_index": deliver.warmup_day_index(rt),
                "note": (
                    "Календарь = план/бэклог. За сутки SMTP уйдёт не больше "
                    f"effective_daily_limit={effective} (warmup + OUTREACH_DAILY_LIMIT). "
                    "Нажмите «Разложить на будни», если один день перегружен (выходные пустые)."
                ),
            }
            return snap

        class PaceBody(BaseModel):
            dry_run: bool = False
            workdays: int = 14
            horizon_days: int | None = None  # legacy alias

        @router.post("/pace-queue")
        def pace_queue(body: PaceBody | None = None) -> dict[str, Any]:
            """Spread pending first-touch across weekdays (skip weekends)."""
            from modules.deliverability import DeliverabilityStore
            from modules.sequences.pace import pace_first_touch_queue
            from outbox import OutboxStore
            from core.paths import DATA_DIR, SETTINGS_DB
            from runtime_settings import RuntimeSettings

            payload = body or PaceBody()
            outbox = OutboxStore(DATA_DIR / "outbox.db")
            rt = RuntimeSettings(SETTINGS_DB)
            deliver = DeliverabilityStore()
            configured = rt.get_int("OUTREACH_DAILY_LIMIT", 15)
            effective = deliver.effective_daily_limit(rt, configured)
            workdays = int(payload.workdays or payload.horizon_days or 14)
            return pace_first_touch_queue(
                outbox,
                settings=rt,
                effective_daily_limit=effective,
                workdays=max(7, min(workdays, 60)),
                dry_run=bool(payload.dry_run),
            )

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
