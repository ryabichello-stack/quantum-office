"""Sending Accounts registry + protected corporate domains.

Cold / marketing campaigns must not use protected domains (e.g. quantumlabs.ru)
until a dedicated marketing account is ACTIVE. Corporate SMTP stays for
transactional / ops notifies / explicit oneshot tests.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.sending_accounts")

STATUSES = frozenset({"ACTIVE", "WARNING", "PAUSED", "BLOCKED", "CONFIGURATION_ERROR"})
SENDING_TYPES = frozenset({"corporate", "transactional", "marketing"})

DEFAULT_PROTECTED = ("quantumlabs.ru",)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def domain_of(email: str) -> str:
    return (email or "").strip().lower().split("@")[-1]


class SendingAccountsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()
        self.ensure_defaults()

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
                CREATE TABLE IF NOT EXISTS protected_domains (
                    domain TEXT PRIMARY KEY,
                    reason TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sending_accounts (
                    account_id TEXT PRIMARY KEY,
                    domain TEXT NOT NULL,
                    email TEXT NOT NULL,
                    provider TEXT NOT NULL DEFAULT '',
                    sending_type TEXT NOT NULL DEFAULT 'corporate',
                    dkim_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    spf_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    dmarc_status TEXT NOT NULL DEFAULT 'UNKNOWN',
                    health_status TEXT NOT NULL DEFAULT 'CONFIGURATION_ERROR',
                    daily_limit INTEGER NOT NULL DEFAULT 0,
                    sent_today INTEGER NOT NULL DEFAULT 0,
                    bounce_rate REAL NOT NULL DEFAULT 0,
                    complaint_rate REAL NOT NULL DEFAULT 0,
                    last_checked_at TEXT,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    marketing_allowed INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS reputation_incidents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id TEXT,
                    campaign TEXT,
                    kind TEXT NOT NULL,
                    detail TEXT NOT NULL DEFAULT '',
                    action TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )
                """
            )

    def ensure_defaults(self) -> None:
        now = _utc_now()
        with self.connect() as conn:
            for d in DEFAULT_PROTECTED:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO protected_domains(domain, reason, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (d, "corporate_mailbox", now),
                )
        # Mirror env mailbox as corporate legacy account (not for cold marketing).
        email = (os.getenv("MAIL_USERNAME") or "office@quantumlabs.ru").strip().lower()
        dom = domain_of(email) or "quantumlabs.ru"
        provider = (os.getenv("MAIL_SMTP_HOST") or "smtp.mail.ru").strip()
        protected = self.is_protected_domain(dom)
        with self.connect() as conn:
            row = conn.execute(
                "SELECT account_id FROM sending_accounts WHERE account_id = 'legacy'"
            ).fetchone()
            if not row:
                conn.execute(
                    """
                    INSERT INTO sending_accounts(
                        account_id, domain, email, provider, sending_type,
                        dkim_status, spf_status, dmarc_status, health_status,
                        daily_limit, sent_today, bounce_rate, complaint_rate,
                        last_checked_at, enabled, marketing_allowed, notes,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'UNKNOWN', 'UNKNOWN', 'UNKNOWN', ?,
                              ?, 0, 0, 0, NULL, 1, ?, ?, ?, ?)
                    """,
                    (
                        "legacy",
                        dom,
                        email,
                        provider,
                        "corporate",
                        "WARNING" if protected else "ACTIVE",
                        15,
                        0 if protected else 1,
                        (
                            "Corporate mailbox. Protected domain — cold marketing blocked "
                            "until a dedicated marketing sending account is ACTIVE."
                            if protected
                            else "Legacy SMTP account"
                        ),
                        now,
                        now,
                    ),
                )
            else:
                # Keep protected corporate accounts from being used for marketing.
                if protected:
                    conn.execute(
                        """
                        UPDATE sending_accounts
                        SET marketing_allowed = 0,
                            sending_type = 'corporate',
                            notes = CASE
                              WHEN notes LIKE '%Protected domain%' THEN notes
                              ELSE ?
                            END,
                            updated_at = ?
                        WHERE account_id = 'legacy'
                        """,
                        (
                            "Corporate mailbox. Protected domain — cold marketing blocked "
                            "until a dedicated marketing sending account is ACTIVE.",
                            now,
                        ),
                    )

    def list_protected_domains(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT domain FROM protected_domains ORDER BY domain"
            ).fetchall()
        return [str(r["domain"]) for r in rows]

    def is_protected_domain(self, domain: str) -> bool:
        d = (domain or "").strip().lower()
        if not d:
            return False
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM protected_domains WHERE domain = ?", (d,)
            ).fetchone()
        return bool(row)

    def add_protected_domain(self, domain: str, *, reason: str = "manual") -> None:
        d = (domain or "").strip().lower()
        if not d:
            raise ValueError("domain required")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO protected_domains(domain, reason, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(domain) DO UPDATE SET reason = excluded.reason
                """,
                (d, (reason or "manual")[:300], _utc_now()),
            )

    def list_accounts(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM sending_accounts ORDER BY account_id"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sending_accounts WHERE account_id = ?",
                ((account_id or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def upsert_account(self, account_id: str, **fields: Any) -> dict[str, Any]:
        aid = (account_id or "").strip()
        if not aid:
            raise ValueError("account_id required")
        existing = self.get(aid) or {
            "account_id": aid,
            "domain": "",
            "email": "",
            "provider": "",
            "sending_type": "marketing",
            "dkim_status": "UNKNOWN",
            "spf_status": "UNKNOWN",
            "dmarc_status": "UNKNOWN",
            "health_status": "CONFIGURATION_ERROR",
            "daily_limit": 0,
            "sent_today": 0,
            "bounce_rate": 0.0,
            "complaint_rate": 0.0,
            "last_checked_at": None,
            "enabled": 0,
            "marketing_allowed": 0,
            "notes": "",
            "created_at": _utc_now(),
        }
        data = {**existing, **{k: v for k, v in fields.items() if v is not None}}
        data["account_id"] = aid
        data["updated_at"] = _utc_now()
        if data.get("sending_type") not in SENDING_TYPES:
            data["sending_type"] = "marketing"
        if data.get("health_status") not in STATUSES:
            data["health_status"] = "CONFIGURATION_ERROR"
        # Protected domain can never be marketing_allowed.
        if self.is_protected_domain(str(data.get("domain") or domain_of(str(data.get("email") or "")))):
            data["marketing_allowed"] = 0
            if data.get("sending_type") == "marketing":
                data["sending_type"] = "corporate"
                data["health_status"] = "BLOCKED"
        cols = [
            "account_id",
            "domain",
            "email",
            "provider",
            "sending_type",
            "dkim_status",
            "spf_status",
            "dmarc_status",
            "health_status",
            "daily_limit",
            "sent_today",
            "bounce_rate",
            "complaint_rate",
            "last_checked_at",
            "enabled",
            "marketing_allowed",
            "notes",
            "created_at",
            "updated_at",
        ]
        vals = []
        for c in cols:
            v = data.get(c)
            if c in ("enabled", "marketing_allowed"):
                vals.append(1 if v in (True, 1, "1", "true") else 0)
            else:
                vals.append(v)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO sending_accounts({", ".join(cols)})
                VALUES ({", ".join("?" for _ in cols)})
                ON CONFLICT(account_id) DO UPDATE SET
                  domain=excluded.domain,
                  email=excluded.email,
                  provider=excluded.provider,
                  sending_type=excluded.sending_type,
                  dkim_status=excluded.dkim_status,
                  spf_status=excluded.spf_status,
                  dmarc_status=excluded.dmarc_status,
                  health_status=excluded.health_status,
                  daily_limit=excluded.daily_limit,
                  sent_today=excluded.sent_today,
                  bounce_rate=excluded.bounce_rate,
                  complaint_rate=excluded.complaint_rate,
                  last_checked_at=excluded.last_checked_at,
                  enabled=excluded.enabled,
                  marketing_allowed=excluded.marketing_allowed,
                  notes=excluded.notes,
                  updated_at=excluded.updated_at
                """,
                vals,
            )
        return self.get(aid) or {}

    def set_health(self, account_id: str, status: str, *, detail: str = "") -> None:
        st = (status or "").upper()
        if st not in STATUSES:
            raise ValueError(f"invalid status {status}")
        self.upsert_account(account_id, health_status=st, notes=detail or None)
        if detail:
            self.record_incident(
                account_id=account_id,
                kind="health_status",
                detail=detail,
                action=f"set:{st}",
            )

    def record_incident(
        self,
        *,
        account_id: str | None,
        kind: str,
        detail: str,
        action: str = "",
        campaign: str = "",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO reputation_incidents(
                    account_id, campaign, kind, detail, action, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    account_id,
                    campaign or "",
                    (kind or "incident")[:80],
                    (detail or "")[:1000],
                    (action or "")[:200],
                    _utc_now(),
                ),
            )

    def list_incidents(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM reputation_incidents
                ORDER BY id DESC LIMIT ?
                """,
                (max(1, min(limit, 500)),),
            ).fetchall()
        return [dict(r) for r in rows]

    def active_marketing_account(self) -> dict[str, Any] | None:
        """Return first enabled ACTIVE marketing account that is allowed to send cold mail."""
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM sending_accounts
                WHERE enabled = 1
                  AND marketing_allowed = 1
                  AND sending_type = 'marketing'
                  AND health_status = 'ACTIVE'
                ORDER BY account_id
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row else None

    def marketing_send_gate(
        self,
        *,
        from_email: str | None = None,
        allow_protected_override: bool = False,
    ) -> tuple[bool, str, dict[str, Any] | None]:
        """Decide whether cold/marketing send may proceed.

        Protected corporate domains are never used for mass marketing unless an
        explicit override is set (ops emergency only — default off).
        """
        email = (from_email or os.getenv("MAIL_USERNAME") or "").strip().lower()
        dom = domain_of(email)
        mkt = self.active_marketing_account()
        if mkt:
            return True, "ok", mkt

        if allow_protected_override:
            return True, "override_protected", self.get("legacy")

        if self.is_protected_domain(dom):
            return (
                False,
                (
                    f"protected_domain:{dom} — cold marketing from corporate mailbox "
                    "is blocked. Configure an ACTIVE marketing Sending Account "
                    "(separate domain) before Play."
                ),
                self.get("legacy"),
            )

        # Non-protected From without registry marketing account: still refuse by default
        # until an explicit marketing account is configured (safe default).
        return (
            False,
            "no_active_marketing_account — add Sending Account with marketing_allowed=1",
            None,
        )


class SendingAccountsModule:
    name = "sending_accounts"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = SendingAccountsStore()
        self._settings: Any = None

    def init_db(self) -> None:
        self.store.init_db()
        self.store.ensure_defaults()

    def on_startup(self, ctx: AppContext) -> None:
        self._settings = ctx.settings
        ctx.extras["sending_accounts"] = self.store
        self.store.ensure_defaults()
        logger.info(
            "sending_accounts ready protected=%s accounts=%s",
            self.store.list_protected_domains(),
            len(self.store.list_accounts()),
        )

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        mkt = self.store.active_marketing_account()
        return {
            "ok": True,
            "protected_domains": self.store.list_protected_domains(),
            "marketing_ready": bool(mkt),
            "accounts": len(self.store.list_accounts()),
        }

    def register_routes(self, router: Any) -> None:
        from pydantic import BaseModel, Field

        @router.get("/accounts")
        def accounts() -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_accounts()}

        @router.get("/protected-domains")
        def protected() -> dict[str, Any]:
            return {"ok": True, "domains": self.store.list_protected_domains()}

        class ProtBody(BaseModel):
            domain: str = Field(..., min_length=3)
            reason: str = "manual"

        @router.post("/protected-domains")
        def add_prot(body: ProtBody) -> dict[str, Any]:
            self.store.add_protected_domain(body.domain, reason=body.reason)
            return {"ok": True, "domains": self.store.list_protected_domains()}

        @router.get("/marketing-gate")
        def gate() -> dict[str, Any]:
            override = False
            if self._settings is not None:
                override = bool(
                    self._settings.get_bool("MARKETING_ALLOW_PROTECTED_DOMAIN", False)
                )
            ok, why, acc = self.store.marketing_send_gate(
                allow_protected_override=override
            )
            return {
                "ok": ok,
                "reason": why,
                "account": acc,
                "override": override,
            }

        @router.get("/incidents")
        def incidents(limit: int = 50) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_incidents(limit=limit)}

        class AccBody(BaseModel):
            account_id: str
            domain: str
            email: str
            provider: str = ""
            sending_type: str = "marketing"
            daily_limit: int = 0
            enabled: bool = False
            marketing_allowed: bool = False
            health_status: str = "CONFIGURATION_ERROR"
            notes: str = ""

        @router.post("/accounts")
        def upsert(body: AccBody) -> dict[str, Any]:
            row = self.store.upsert_account(
                body.account_id,
                domain=body.domain,
                email=body.email,
                provider=body.provider,
                sending_type=body.sending_type,
                daily_limit=body.daily_limit,
                enabled=body.enabled,
                marketing_allowed=body.marketing_allowed,
                health_status=body.health_status,
                notes=body.notes,
            )
            return {"ok": True, "account": row}

        class HealthBody(BaseModel):
            status: str
            detail: str = ""

        @router.post("/accounts/{account_id}/health")
        def set_health(account_id: str, body: HealthBody) -> dict[str, Any]:
            self.store.set_health(account_id, body.status, detail=body.detail)
            return {"ok": True, "account": self.store.get(account_id)}
