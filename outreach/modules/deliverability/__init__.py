"""Deliverability / anti-ban controls (independent module).

Practices encoded here:
- kill switch + daily cap
- warmup ramp (effective daily limit grows slowly)
- per-recipient-domain throttle
- company-level first-touch guard (protect primary domain)
- suppression list (hard bounce / unsubscribe / manual)
- mailbox pause / stop rules on bounce health
- min/max jitter delay (enforced by sender using settings)
"""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext
from modules.deliverability.bounce import BounceClass, classify_bounce

logger = logging.getLogger("ava-outreach.deliverability")

# Consumer ISPs: half a B2B list may be @mail.ru — do not treat like corporate domain.
SHARED_MAILBOX_DOMAINS = frozenset(
    {
        "mail.ru",
        "inbox.ru",
        "list.ru",
        "bk.ru",
        "internet.ru",
        "xmail.ru",
        "yandex.ru",
        "yandex.com",
        "ya.ru",
        "gmail.com",
        "googlemail.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "icloud.com",
        "me.com",
        "rambler.ru",
        "ro.ru",
        "vk.com",
        "ok.ru",
    }
)


def is_shared_mailbox_domain(domain: str) -> bool:
    d = (domain or "").strip().lower()
    if not d:
        return False
    if d in SHARED_MAILBOX_DOMAINS:
        return True
    return any(d.endswith("." + root) for root in ("mail.ru", "yandex.ru", "yandex.com"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today() -> str:
    return date.today().isoformat()


@dataclass
class GuardDecision:
    allow: bool
    reason: str
    effective_daily_limit: int
    sent_today: int
    domain_sent_today: int


class DeliverabilityStore:
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
                CREATE TABLE IF NOT EXISTS suppression (
                    email TEXT PRIMARY KEY,
                    reason TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'manual',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS domain_sends (
                    day TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, domain)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS warmup_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    start_day TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS oneshot_sends (
                    day TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mailbox_pause (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    paused INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bounce_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    category TEXT NOT NULL,
                    code TEXT NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    raw TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS company_sends (
                    day TEXT NOT NULL,
                    company_id TEXT NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, company_id)
                )
                """
            )

    def is_paused(self) -> tuple[bool, str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT paused, reason FROM mailbox_pause WHERE id = 1"
            ).fetchone()
        if not row:
            return False, ""
        return bool(row["paused"]), str(row["reason"] or "")

    def pause_mailbox(self, reason: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_pause(id, paused, reason, updated_at)
                VALUES (1, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    paused = 1,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                ((reason or "manual")[:500], _utc_now()),
            )
        logger.warning("mailbox PAUSED: %s", reason)
        try:
            from core.paths import SETTINGS_DB
            from ops_notify import notify_mailbox_paused
            from runtime_settings import RuntimeSettings

            notify_mailbox_paused(reason=reason, settings=RuntimeSettings(SETTINGS_DB))
        except Exception:  # noqa: BLE001
            logger.debug("ops notify on mailbox pause failed", exc_info=True)

    def resume_mailbox(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO mailbox_pause(id, paused, reason, updated_at)
                VALUES (1, 0, '', ?)
                ON CONFLICT(id) DO UPDATE SET
                    paused = 0,
                    reason = '',
                    updated_at = excluded.updated_at
                """,
                (_utc_now(),),
            )
        logger.info("mailbox resumed")

    def record_bounce_event(
        self,
        *,
        email: str,
        classified: BounceClass,
        raw: str | None = None,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bounce_events(email, category, code, reason, raw, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    (email or "").strip().lower(),
                    classified.category,
                    classified.code,
                    classified.reason,
                    (raw or "")[:1000],
                    _utc_now(),
                ),
            )

    def bounce_stats(self, *, last_n: int = 50) -> dict[str, Any]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT category FROM bounce_events
                ORDER BY id DESC LIMIT ?
                """,
                (max(1, last_n),),
            ).fetchall()
            today = _today()
            day_rows = conn.execute(
                """
                SELECT category, COUNT(*) AS n FROM bounce_events
                WHERE created_at LIKE ?
                GROUP BY category
                """,
                (f"{today}%",),
            ).fetchall()
        cats = {"hard": 0, "soft": 0, "policy": 0, "auth": 0, "unknown": 0}
        for r in rows:
            c = str(r["category"])
            if c in cats:
                cats[c] += 1
            else:
                cats["unknown"] += 1
        day = {str(r["category"]): int(r["n"]) for r in day_rows}
        n = len(rows)
        hard = cats["hard"] + cats["unknown"]  # unknown counted hard for rate
        rate = (hard / n * 100.0) if n else 0.0
        return {
            "window": n,
            "categories": cats,
            "hard_rate_pct": round(rate, 2),
            "today": day,
        }

    def apply_stop_rules(self, settings: Any = None) -> dict[str, Any]:
        """Pause mailbox when bounce health is bad. Absolute + percentage gates."""
        paused, reason = self.is_paused()
        if paused:
            return {"paused": True, "reason": reason, "triggered": False}

        stats = self.bounce_stats(last_n=50)
        cats = stats["categories"]
        hard_n = int(cats.get("hard", 0)) + int(cats.get("unknown", 0))
        window = int(stats["window"])
        rate = float(stats["hard_rate_pct"])
        today = stats.get("today") or {}
        policy_today = int(today.get("policy", 0)) + int(today.get("auth", 0))

        # Absolute + percentage: avoid pause on tiny samples
        if window >= 20 and hard_n >= 3 and rate >= 3.0:
            msg = f"stop_rule:hard_bounce rate={rate}% n={hard_n}/{window}"
            self.pause_mailbox(msg)
            return {"paused": True, "reason": msg, "triggered": True, "stats": stats}

        if policy_today >= 2:
            msg = f"stop_rule:policy_blocks_today={policy_today}"
            self.pause_mailbox(msg)
            return {"paused": True, "reason": msg, "triggered": True, "stats": stats}

        if int(today.get("auth", 0)) >= 1:
            msg = "stop_rule:authentication_failure"
            self.pause_mailbox(msg)
            return {"paused": True, "reason": msg, "triggered": True, "stats": stats}

        return {"paused": False, "reason": "", "triggered": False, "stats": stats}

    def handle_bounce(
        self,
        *,
        email: str,
        raw_reason: str | None,
    ) -> BounceClass:
        classified = classify_bounce(raw_reason)
        self.record_bounce_event(email=email, classified=classified, raw=raw_reason)
        if classified.suppress:
            self.add_suppression(
                email,
                reason=f"hard_bounce:{classified.reason}",
                source="imap-dsn",
            )
        if classified.pause_mailbox:
            self.pause_mailbox(f"bounce:{classified.category}:{classified.reason}")
        else:
            self.apply_stop_rules()
        return classified

    def company_sent_today(self, company_id: str) -> int:
        cid = (company_id or "").strip()
        if not cid:
            return 0
        with self.connect() as conn:
            row = conn.execute(
                "SELECT count FROM company_sends WHERE day = ? AND company_id = ?",
                (_today(), cid),
            ).fetchone()
        return int(row["count"]) if row else 0

    def bump_company(self, company_id: str) -> None:
        cid = (company_id or "").strip()
        if not cid:
            return
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO company_sends(day, company_id, count)
                VALUES (?, ?, 1)
                ON CONFLICT(day, company_id) DO UPDATE SET count = count + 1
                """,
                (_today(), cid),
            )

    def is_suppressed(self, email: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT reason FROM suppression WHERE lower(email) = lower(?)",
                (email.strip(),),
            ).fetchone()
        return str(row["reason"]) if row else None

    def add_suppression(self, email: str, *, reason: str, source: str = "manual") -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO suppression(email, reason, source, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(email) DO UPDATE SET
                  reason = excluded.reason,
                  source = excluded.source
                """,
                (email.strip().lower(), reason, source, _utc_now()),
            )
        try:
            from modules.consent import ConsentLedgerStore, record_consent_from_suppression

            record_consent_from_suppression(
                ConsentLedgerStore(),
                email=email,
                reason=reason,
                source=source,
            )
        except Exception:  # noqa: BLE001
            logger.debug("consent ledger on suppression failed", exc_info=True)

    def remove_suppression(self, email: str) -> bool:
        with self.connect() as conn:
            cur = conn.execute(
                "DELETE FROM suppression WHERE lower(email) = lower(?)",
                (email.strip(),),
            )
            return bool(cur.rowcount)

    def list_suppression(self, limit: int = 200) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM suppression ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def ensure_warmup_start(self, settings: Any) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT start_day FROM warmup_state WHERE id = 1").fetchone()
            if row:
                return str(row["start_day"])
            start = settings.get("WARMUP_START_DAY", None) if settings else None
            start = (start or _today()).strip()
            conn.execute(
                """
                INSERT INTO warmup_state(id, start_day, updated_at)
                VALUES (1, ?, ?)
                """,
                (start, _utc_now()),
            )
            return start

    def warmup_day_index(self, settings: Any) -> int:
        start = self.ensure_warmup_start(settings)
        try:
            start_d = date.fromisoformat(start[:10])
        except ValueError:
            start_d = date.today()
        return max(0, (date.today() - start_d).days)

    def effective_daily_limit(self, settings: Any, configured: int) -> int:
        # Primary corporate domain: keep configured low; warmup even lower at start.
        if not settings or not settings.get_bool("WARMUP_ENABLED", True):
            return configured
        day = self.warmup_day_index(settings)
        # Conservative ramp for office@ — never jump to 20 on day 1
        ramp = [3, 5, 5, 8, 8, 10, 12, 15]
        if day < len(ramp):
            return min(configured, ramp[day])
        extra = ((day - len(ramp)) // 3) * 2
        return min(configured, max(ramp[-1], ramp[-1] + extra))

    def domain_of(self, email: str) -> str:
        return email.strip().lower().split("@")[-1]

    def domain_count_today(self, domain: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT count FROM domain_sends WHERE day = ? AND domain = ?",
                (_today(), domain),
            ).fetchone()
        return int(row["count"]) if row else 0

    def bump_domain(self, domain: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO domain_sends(day, domain, count)
                VALUES (?, ?, 1)
                ON CONFLICT(day, domain) DO UPDATE SET count = count + 1
                """,
                (_today(), domain),
            )

    def decide(
        self,
        *,
        email: str,
        settings: Any,
        sent_today: int,
        configured_daily_limit: int,
        company_id: str | None = None,
        company_already_contacted: bool = False,
    ) -> GuardDecision:
        effective = self.effective_daily_limit(settings, configured_daily_limit)
        domain = self.domain_of(email)
        domain_n = self.domain_count_today(domain)
        # Corporate domains: keep low. Shared ISPs (mail.ru…): allow up to daily limit.
        corp_cap = 2
        shared_cap = effective
        if settings is not None:
            corp_cap = settings.get_int("DOMAIN_DAILY_CAP", 2)
            shared_override = settings.get_int("DOMAIN_SHARED_DAILY_CAP", 0)
            if shared_override and shared_override > 0:
                shared_cap = shared_override
            else:
                shared_cap = effective
        domain_cap = shared_cap if is_shared_mailbox_domain(domain) else corp_cap
        company_cap = 1
        if settings is not None:
            company_cap = settings.get_int("COMPANY_DAILY_CAP", 1)

        paused, pause_reason = self.is_paused()
        if paused:
            return GuardDecision(
                False, f"mailbox_paused:{pause_reason}", effective, sent_today, domain_n
            )

        reason = self.is_suppressed(email)
        if reason:
            return GuardDecision(False, f"suppressed:{reason}", effective, sent_today, domain_n)
        if company_already_contacted:
            return GuardDecision(
                False, "company_already_contacted", effective, sent_today, domain_n
            )
        if company_id and self.company_sent_today(company_id) >= company_cap:
            return GuardDecision(
                False,
                f"company_cap:{company_id}:{company_cap}",
                effective,
                sent_today,
                domain_n,
            )
        if sent_today >= effective:
            return GuardDecision(
                False, f"daily_limit:{effective}", effective, sent_today, domain_n
            )
        if domain_n >= domain_cap:
            return GuardDecision(
                False, f"domain_cap:{domain}:{domain_cap}", effective, sent_today, domain_n
            )
        return GuardDecision(True, "ok", effective, sent_today, domain_n)

    def oneshot_today(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT count FROM oneshot_sends WHERE day = ?",
                (_today(),),
            ).fetchone()
        return int(row["count"]) if row else 0

    def bump_oneshot(self) -> int:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO oneshot_sends(day, count) VALUES (?, 1)
                ON CONFLICT(day) DO UPDATE SET count = count + 1
                """,
                (_today(),),
            )
        return self.oneshot_today()

    def stats(self, settings: Any, configured: int) -> dict[str, Any]:
        with self.connect() as conn:
            supp = conn.execute("SELECT COUNT(*) AS n FROM suppression").fetchone()["n"]
            domains = conn.execute(
                "SELECT COUNT(*) AS n FROM domain_sends WHERE day = ?",
                (_today(),),
            ).fetchone()["n"]
        oneshot_limit = 5
        if settings is not None:
            oneshot_limit = settings.get_int("ONESHOT_DAILY_LIMIT", 25)
        paused, pause_reason = self.is_paused()
        return {
            "suppressed": int(supp),
            "domains_touched_today": int(domains),
            "warmup_enabled": bool(settings.get_bool("WARMUP_ENABLED", True))
            if settings
            else True,
            "warmup_day_index": self.warmup_day_index(settings) if settings else 0,
            "effective_daily_limit": self.effective_daily_limit(settings, configured),
            "configured_daily_limit": configured,
            "domain_daily_cap": settings.get_int("DOMAIN_DAILY_CAP", 2) if settings else 2,
            "domain_shared_daily_cap": (
                settings.get_int("DOMAIN_SHARED_DAILY_CAP", 0) if settings else 0
            )
            or (self.effective_daily_limit(settings, configured) if settings else configured),
            "shared_mailbox_note": "mail.ru/yandex/gmail… используют shared cap (= дневной лимит)",
            "company_daily_cap": settings.get_int("COMPANY_DAILY_CAP", 1) if settings else 1,
            "oneshot_today": self.oneshot_today(),
            "oneshot_daily_limit": oneshot_limit,
            "mailbox_paused": paused,
            "mailbox_pause_reason": pause_reason,
            "bounce_stats": self.bounce_stats(last_n=50),
            "primary_domain_mode": True,
            "note": (
                "Sending from primary corporate mailbox — conservative limits "
                "and stop rules protect domain reputation."
            ),
        }


class DeliverabilityModule:
    name = "deliverability"
    version = "1.1.0"

    def __init__(self) -> None:
        self.store = DeliverabilityStore()
        self._settings: Any = None

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        self._settings = ctx.settings
        ctx.extras["deliverability"] = self.store
        if ctx.settings:
            self.store.ensure_warmup_start(ctx.settings)
        logger.info("deliverability module ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        n = len(self.store.list_suppression(limit=5000))
        paused, reason = self.store.is_paused()
        return {"ok": not paused, "suppressed": n, "paused": paused, "pause_reason": reason}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException
        from pydantic import BaseModel

        @router.get("/stats")
        def stats() -> dict[str, Any]:
            configured = 15
            if self._settings is not None:
                configured = self._settings.get_int("OUTREACH_DAILY_LIMIT", 15)
            return {
                "ok": True,
                "stats": self.store.stats(self._settings, configured),
            }

        @router.get("/health-rules")
        def health_rules() -> dict[str, Any]:
            return {"ok": True, **self.store.apply_stop_rules(self._settings)}

        @router.post("/pause")
        def pause(reason: str = "manual") -> dict[str, Any]:
            self.store.pause_mailbox(reason or "manual")
            return {"ok": True, "paused": True}

        @router.post("/resume")
        def resume() -> dict[str, Any]:
            self.store.resume_mailbox()
            return {"ok": True, "paused": False}

        class SuppBody(BaseModel):
            email: str
            reason: str = "manual"

        @router.get("/suppression")
        def list_supp(limit: int = 200) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_suppression(limit=limit)}

        @router.post("/suppression")
        def add_supp(body: SuppBody) -> dict[str, Any]:
            self.store.add_suppression(body.email, reason=body.reason, source="ui")
            return {"ok": True}

        @router.delete("/suppression/{email}")
        def del_supp(email: str) -> dict[str, Any]:
            ok = self.store.remove_suppression(email)
            if not ok:
                raise HTTPException(404, "not found")
            return {"ok": True}
