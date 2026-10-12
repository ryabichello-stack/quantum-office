"""Unified contact policy between email outreach and AVA telephony."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.policy")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


class ContactPolicyStore:
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
                CREATE TABLE IF NOT EXISTS contact_policy (
                    company_id TEXT PRIMARY KEY,
                    do_not_email INTEGER NOT NULL DEFAULT 0,
                    do_not_call INTEGER NOT NULL DEFAULT 0,
                    last_email_at TEXT,
                    last_call_at TEXT,
                    last_reply_at TEXT,
                    last_call_result TEXT,
                    active_deal INTEGER NOT NULL DEFAULT 0,
                    next_allowed_email_at TEXT,
                    next_allowed_call_at TEXT,
                    primary_email TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            # Consent / legal basis for marketing (ФЗ «О рекламе» art. 18).
            cols = {
                r[1] for r in conn.execute("PRAGMA table_info(contact_policy)").fetchall()
            }
            for col, decl in (
                ("consent_status", "TEXT NOT NULL DEFAULT 'unknown'"),
                ("consent_source", "TEXT NOT NULL DEFAULT ''"),
                ("consent_timestamp", "TEXT"),
                ("consent_evidence", "TEXT NOT NULL DEFAULT ''"),
                ("source_url", "TEXT NOT NULL DEFAULT ''"),
                ("unsubscribe_status", "TEXT NOT NULL DEFAULT ''"),
                ("last_delivery_status", "TEXT NOT NULL DEFAULT ''"),
                ("suppression_reason", "TEXT NOT NULL DEFAULT ''"),
            ):
                if col not in cols:
                    conn.execute(f"ALTER TABLE contact_policy ADD COLUMN {col} {decl}")

    def get(self, company_id: str) -> dict[str, Any] | None:
        cid = (company_id or "").strip()
        if not cid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM contact_policy WHERE company_id = ?", (cid,)
            ).fetchone()
        return dict(row) if row else None

    def upsert(self, company_id: str, **fields: Any) -> dict[str, Any]:
        cid = (company_id or "").strip()
        if not cid:
            raise ValueError("company_id required")
        existing = self.get(cid) or {}
        data = {**existing, **{k: v for k, v in fields.items() if v is not None}}
        data["company_id"] = cid
        data["updated_at"] = _utc_now()
        cols = (
            "company_id",
            "do_not_email",
            "do_not_call",
            "last_email_at",
            "last_call_at",
            "last_reply_at",
            "last_call_result",
            "active_deal",
            "next_allowed_email_at",
            "next_allowed_call_at",
            "primary_email",
            "consent_status",
            "consent_source",
            "consent_timestamp",
            "consent_evidence",
            "source_url",
            "unsubscribe_status",
            "last_delivery_status",
            "suppression_reason",
            "updated_at",
        )
        vals = []
        for c in cols:
            v = data.get(c)
            if c in ("do_not_email", "do_not_call", "active_deal"):
                vals.append(1 if v in (True, 1, "1", "true") else 0)
            elif c == "consent_status":
                vals.append((v or "unknown"))
            elif c in (
                "consent_source",
                "consent_evidence",
                "source_url",
                "unsubscribe_status",
                "last_delivery_status",
                "suppression_reason",
            ):
                vals.append("" if v is None else v)
            else:
                vals.append(v)
        with self.connect() as conn:
            conn.execute(
                f"""
                INSERT INTO contact_policy({", ".join(cols)})
                VALUES ({", ".join("?" for _ in cols)})
                ON CONFLICT(company_id) DO UPDATE SET
                  do_not_email=excluded.do_not_email,
                  do_not_call=excluded.do_not_call,
                  last_email_at=COALESCE(excluded.last_email_at, contact_policy.last_email_at),
                  last_call_at=COALESCE(excluded.last_call_at, contact_policy.last_call_at),
                  last_reply_at=COALESCE(excluded.last_reply_at, contact_policy.last_reply_at),
                  last_call_result=COALESCE(excluded.last_call_result, contact_policy.last_call_result),
                  active_deal=excluded.active_deal,
                  next_allowed_email_at=COALESCE(excluded.next_allowed_email_at, contact_policy.next_allowed_email_at),
                  next_allowed_call_at=COALESCE(excluded.next_allowed_call_at, contact_policy.next_allowed_call_at),
                  primary_email=COALESCE(excluded.primary_email, contact_policy.primary_email),
                  consent_status=COALESCE(excluded.consent_status, contact_policy.consent_status),
                  consent_source=COALESCE(excluded.consent_source, contact_policy.consent_source),
                  consent_timestamp=COALESCE(excluded.consent_timestamp, contact_policy.consent_timestamp),
                  consent_evidence=COALESCE(excluded.consent_evidence, contact_policy.consent_evidence),
                  source_url=COALESCE(excluded.source_url, contact_policy.source_url),
                  unsubscribe_status=COALESCE(excluded.unsubscribe_status, contact_policy.unsubscribe_status),
                  last_delivery_status=COALESCE(excluded.last_delivery_status, contact_policy.last_delivery_status),
                  suppression_reason=COALESCE(excluded.suppression_reason, contact_policy.suppression_reason),
                  updated_at=excluded.updated_at
                """,
                vals,
            )
        return self.get(cid) or {}

    def allow_marketing_consent(
        self,
        company_id: str,
        *,
        require_consent: bool = True,
    ) -> tuple[bool, str]:
        """Marketing send gate. Presence in CBR registry ≠ advertising consent."""
        if not require_consent:
            return True, "consent_not_required"
        pol = self.get(company_id)
        if not pol:
            return False, "consent:unknown_no_policy_row"
        status = (pol.get("consent_status") or "unknown").strip().lower()
        if status == "granted":
            return True, "consent:granted"
        if status == "denied":
            return False, "consent:denied"
        if (pol.get("unsubscribe_status") or "").lower() in ("unsubscribed", "1", "true"):
            return False, "consent:unsubscribed"
        return False, f"consent:{status or 'unknown'}"

    def set_consent(
        self,
        company_id: str,
        *,
        status: str,
        source: str = "",
        evidence: str = "",
        source_url: str = "",
    ) -> dict[str, Any]:
        st = (status or "unknown").strip().lower()
        if st not in ("unknown", "granted", "denied", "legacy_unverified"):
            raise ValueError("invalid consent_status")
        return self.upsert(
            company_id,
            consent_status=st,
            consent_source=(source or "")[:300],
            consent_evidence=(evidence or "")[:1000],
            consent_timestamp=_utc_now() if st == "granted" else None,
            source_url=(source_url or "")[:500],
        )

    def allow_email(
        self,
        company_id: str,
        *,
        cooldown_days: int = 14,
    ) -> tuple[bool, str]:
        pol = self.get(company_id)
        if not pol:
            return True, "ok"
        if pol.get("do_not_email"):
            return False, "do_not_email"
        nxt = _parse_iso(pol.get("next_allowed_email_at"))
        if nxt and datetime.now(timezone.utc) < nxt:
            return False, f"email_cooldown_until:{nxt.isoformat()}"
        result = (pol.get("last_call_result") or "").lower()
        if result in ("refused", "negative", "not_interested", "unsubscribe"):
            return False, f"call_result:{result}"
        if result in ("meeting", "meeting_booked", "interested", "qualified") and pol.get(
            "active_deal"
        ):
            return False, "active_deal_after_call"
        return True, "ok"

    def note_email_sent(self, company_id: str, *, email: str | None = None) -> None:
        if not company_id:
            return
        self.upsert(
            company_id,
            last_email_at=_utc_now(),
            primary_email=email,
        )

    def note_reply(self, company_id: str, *, stop_email: bool = True) -> None:
        if not company_id:
            return
        fields: dict[str, Any] = {"last_reply_at": _utc_now()}
        if stop_email:
            fields["do_not_email"] = 0  # reply ≠ always dnc; sequence stops separately
            fields["next_allowed_email_at"] = (
                datetime.now(timezone.utc) + timedelta(days=180)
            ).replace(microsecond=0).isoformat()
        self.upsert(company_id, **fields)

    def note_unsubscribe(self, company_id: str) -> None:
        if not company_id:
            return
        self.upsert(
            company_id,
            do_not_email=1,
            last_reply_at=_utc_now(),
            unsubscribe_status="unsubscribed",
            consent_status="denied",
            suppression_reason="unsubscribe",
        )

    def note_call(
        self,
        company_id: str,
        *,
        result: str,
        meeting: bool = False,
        refused: bool = False,
        interested: bool = False,
        cooldown_days_on_refuse: int = 180,
    ) -> None:
        if not company_id:
            return
        fields: dict[str, Any] = {
            "last_call_at": _utc_now(),
            "last_call_result": result,
        }
        if meeting or interested:
            fields["active_deal"] = 1
            fields["next_allowed_email_at"] = (
                datetime.now(timezone.utc) + timedelta(days=30)
            ).replace(microsecond=0).isoformat()
        if refused:
            fields["do_not_email"] = 1
            fields["next_allowed_email_at"] = (
                datetime.now(timezone.utc) + timedelta(days=cooldown_days_on_refuse)
            ).replace(microsecond=0).isoformat()
        self.upsert(company_id, **fields)

    def set_second_contact_cooldown(self, company_id: str, *, days: int = 14) -> None:
        if not company_id:
            return
        self.upsert(
            company_id,
            next_allowed_email_at=(
                datetime.now(timezone.utc) + timedelta(days=max(1, days))
            )
            .replace(microsecond=0)
            .isoformat(),
        )


class PolicyModule:
    name = "policy"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = ContactPolicyStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["policy"] = self.store
        logger.info("policy module ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n = conn.execute("SELECT COUNT(*) AS n FROM contact_policy").fetchone()["n"]
        return {"ok": True, "companies": int(n)}

    def register_routes(self, router: Any) -> None:
        @router.get("/company/{company_id}")
        def get_pol(company_id: str) -> dict[str, Any]:
            return {"ok": True, "policy": self.store.get(company_id)}
