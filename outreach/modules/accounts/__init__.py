"""Account / Person / Lead / Events — Stage 1 Revenue OS core.

Wraps Bitrix clients mirror without replacing it. Local SoT for lifecycle
and inbound identity resolution (Accept R1/R2: local Account + Bitrix ref,
data in outreach modules.db).
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.accounts")

DEFAULT_TENANT = "quantum-labs"

# Canonical CRM statuses from vault / DATA_MAPPING
LIFECYCLE = (
    "NEW",
    "ENRICHED",
    "IN_SEQUENCE",
    "REPLIED",
    "INTERESTED",
    "MEETING_BOOKED",
    "DISQUALIFIED",
    "NO_RESPONSE",
    "BLACKLISTED",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def normalize_email(email: str | None) -> str:
    return (email or "").strip().lower()


def normalize_name(name: str | None) -> str:
    raw = re.sub(r"\s+", " ", (name or "").strip().lower())
    return raw


class AccountStore:
    def __init__(self, db_path: Path | None = None, *, tenant_id: str = DEFAULT_TENANT) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.tenant_id = (tenant_id or DEFAULT_TENANT).strip() or DEFAULT_TENANT
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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    bitrix_company_id TEXT,
                    legal_name TEXT NOT NULL DEFAULT '',
                    brand_name TEXT NOT NULL DEFAULT '',
                    inn TEXT,
                    domain TEXT,
                    industry TEXT,
                    region TEXT,
                    city TEXT,
                    timezone TEXT,
                    lifecycle_status TEXT NOT NULL DEFAULT 'NEW',
                    owner_user_id TEXT,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_accounts_tenant_bitrix
                    ON accounts(tenant_id, bitrix_company_id)
                    WHERE bitrix_company_id IS NOT NULL AND bitrix_company_id != '';
                CREATE INDEX IF NOT EXISTS ix_accounts_lifecycle
                    ON accounts(tenant_id, lifecycle_status);

                CREATE TABLE IF NOT EXISTS people (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    full_name TEXT NOT NULL DEFAULT '',
                    normalized_name TEXT NOT NULL DEFAULT '',
                    location TEXT,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_people_norm
                    ON people(tenant_id, normalized_name);

                CREATE TABLE IF NOT EXISTS employments (
                    id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    decision_role TEXT,
                    is_current INTEGER NOT NULL DEFAULT 1,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_employments_account
                    ON employments(account_id);
                CREATE INDEX IF NOT EXISTS ix_employments_person
                    ON employments(person_id);

                CREATE TABLE IF NOT EXISTS contact_points (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    person_id TEXT,
                    account_id TEXT,
                    type TEXT NOT NULL,
                    value TEXT NOT NULL,
                    display_value TEXT,
                    is_corporate INTEGER NOT NULL DEFAULT 0,
                    verification_status TEXT NOT NULL DEFAULT 'unknown',
                    permission_state TEXT NOT NULL DEFAULT 'unknown',
                    source TEXT,
                    confidence REAL NOT NULL DEFAULT 0.5,
                    last_used_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_contact_points_value
                    ON contact_points(tenant_id, type, value);
                CREATE INDEX IF NOT EXISTS ix_contact_points_person
                    ON contact_points(person_id);
                CREATE INDEX IF NOT EXISTS ix_contact_points_account
                    ON contact_points(account_id);

                CREATE TABLE IF NOT EXISTS leads (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    account_id TEXT,
                    person_id TEXT,
                    source TEXT NOT NULL DEFAULT '',
                    campaign_id TEXT,
                    product TEXT,
                    score REAL,
                    status TEXT NOT NULL DEFAULT 'NEW',
                    owner_user_id TEXT,
                    bitrix_deal_id TEXT,
                    qualification_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_leads_account
                    ON leads(tenant_id, account_id);

                CREATE TABLE IF NOT EXISTS domain_events (
                    id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT '',
                    channel TEXT,
                    account_id TEXT,
                    person_id TEXT,
                    conversation_id TEXT,
                    campaign_id TEXT,
                    correlation_id TEXT,
                    idempotency_key TEXT,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS ux_domain_events_idem
                    ON domain_events(tenant_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL AND idempotency_key != '';
                CREATE INDEX IF NOT EXISTS ix_domain_events_type
                    ON domain_events(tenant_id, event_type, occurred_at);
                """
            )

    # --- accounts ---

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM accounts WHERE id = ? AND tenant_id = ?",
                (account_id, self.tenant_id),
            ).fetchone()
        return dict(row) if row else None

    def get_account_by_bitrix(self, bitrix_company_id: str) -> dict[str, Any] | None:
        bid = (bitrix_company_id or "").strip()
        if not bid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM accounts
                WHERE tenant_id = ? AND bitrix_company_id = ?
                """,
                (self.tenant_id, bid),
            ).fetchone()
        return dict(row) if row else None

    def upsert_account_from_company(self, company: dict[str, Any]) -> dict[str, Any]:
        """Upsert Account from clients.companies row (or company_card company dict)."""
        bid = str(company.get("bitrix_id") or company.get("id") or "").strip()
        title = (company.get("title") or company.get("legal_name") or "").strip()
        now = _utc_now()
        existing = self.get_account_by_bitrix(bid) if bid else None
        lifecycle = existing["lifecycle_status"] if existing else "NEW"
        # Enrichment signal
        if lifecycle == "NEW" and (
            company.get("inn") or company.get("timezone") or company.get("director_name")
        ):
            lifecycle = "ENRICHED"
        aid = existing["id"] if existing else _new_id()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO accounts(
                    id, tenant_id, bitrix_company_id, legal_name, brand_name, inn,
                    domain, region, city, timezone, lifecycle_status,
                    metadata_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    legal_name=excluded.legal_name,
                    brand_name=excluded.brand_name,
                    inn=COALESCE(excluded.inn, accounts.inn),
                    region=COALESCE(excluded.region, accounts.region),
                    city=COALESCE(excluded.city, accounts.city),
                    timezone=COALESCE(excluded.timezone, accounts.timezone),
                    lifecycle_status=CASE
                        WHEN accounts.lifecycle_status IN ('BLACKLISTED','DISQUALIFIED','MEETING_BOOKED','INTERESTED','REPLIED','IN_SEQUENCE')
                        THEN accounts.lifecycle_status
                        ELSE excluded.lifecycle_status
                    END,
                    updated_at=excluded.updated_at
                """,
                (
                    aid,
                    self.tenant_id,
                    bid or None,
                    title,
                    title,
                    (company.get("inn") or None),
                    None,
                    company.get("region"),
                    company.get("city"),
                    company.get("timezone"),
                    lifecycle,
                    json.dumps({"source": "clients"}, ensure_ascii=False),
                    existing["created_at"] if existing else now,
                    now,
                ),
            )
        out = self.get_account(aid)
        assert out
        return out

    def set_lifecycle(self, account_id: str, status: str) -> dict[str, Any] | None:
        status = (status or "").strip().upper()
        if status not in LIFECYCLE:
            raise ValueError(f"invalid lifecycle_status: {status}")
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE accounts SET lifecycle_status = ?, updated_at = ?
                WHERE id = ? AND tenant_id = ?
                """,
                (status, _utc_now(), account_id, self.tenant_id),
            )
        return self.get_account(account_id)

    def list_accounts(self, *, q: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self.connect() as conn:
            if q:
                like = f"%{q.strip().lower()}%"
                rows = conn.execute(
                    """
                    SELECT * FROM accounts
                    WHERE tenant_id = ?
                      AND (
                        lower(legal_name) LIKE ?
                        OR lower(brand_name) LIKE ?
                        OR inn LIKE ?
                        OR bitrix_company_id LIKE ?
                      )
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (self.tenant_id, like, like, like, like, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM accounts WHERE tenant_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (self.tenant_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    # --- people / contact points ---

    def find_person_by_email(self, email: str) -> dict[str, Any] | None:
        em = normalize_email(email)
        if not em:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT p.* FROM people p
                JOIN contact_points cp ON cp.person_id = p.id
                WHERE p.tenant_id = ? AND cp.type = 'email' AND cp.value = ?
                LIMIT 1
                """,
                (self.tenant_id, em),
            ).fetchone()
        return dict(row) if row else None

    def ensure_person(
        self,
        *,
        full_name: str = "",
        email: str | None = None,
        phone: str | None = None,
        account_id: str | None = None,
        title: str = "",
    ) -> dict[str, Any]:
        em = normalize_email(email)
        existing = self.find_person_by_email(em) if em else None
        now = _utc_now()
        if existing:
            pid = existing["id"]
            if full_name and not (existing.get("full_name") or "").strip():
                with self.connect() as conn:
                    conn.execute(
                        """
                        UPDATE people SET full_name = ?, normalized_name = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (full_name.strip(), normalize_name(full_name), now, pid),
                    )
        else:
            pid = _new_id()
            with self.connect() as conn:
                conn.execute(
                    """
                    INSERT INTO people(
                        id, tenant_id, full_name, normalized_name, confidence,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        pid,
                        self.tenant_id,
                        (full_name or "").strip() or (em.split("@")[0] if em else ""),
                        normalize_name(full_name) or normalize_name(em),
                        0.6 if em else 0.4,
                        now,
                        now,
                    ),
                )
        if em:
            self._upsert_contact_point(
                person_id=pid, account_id=account_id, type_="email", value=em
            )
        if phone:
            self._upsert_contact_point(
                person_id=pid,
                account_id=account_id,
                type_="phone",
                value=re.sub(r"\s+", "", phone.strip()),
            )
        if account_id:
            self._ensure_employment(person_id=pid, account_id=account_id, title=title)
        person = self.get_person(pid)
        assert person
        return person

    def get_person(self, person_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM people WHERE id = ? AND tenant_id = ?",
                (person_id, self.tenant_id),
            ).fetchone()
        return dict(row) if row else None

    def _upsert_contact_point(
        self,
        *,
        person_id: str | None,
        account_id: str | None,
        type_: str,
        value: str,
    ) -> None:
        now = _utc_now()
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM contact_points
                WHERE tenant_id = ? AND type = ? AND value = ?
                """,
                (self.tenant_id, type_, value),
            ).fetchone()
            if row:
                conn.execute(
                    """
                    UPDATE contact_points
                    SET person_id = COALESCE(?, person_id),
                        account_id = COALESCE(?, account_id),
                        last_used_at = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (person_id, account_id, now, now, row["id"]),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO contact_points(
                        id, tenant_id, person_id, account_id, type, value,
                        display_value, verification_status, source,
                        created_at, updated_at, last_used_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unknown', 'resolve', ?, ?, ?)
                    """,
                    (
                        _new_id(),
                        self.tenant_id,
                        person_id,
                        account_id,
                        type_,
                        value,
                        value,
                        now,
                        now,
                        now,
                    ),
                )

    def _ensure_employment(self, *, person_id: str, account_id: str, title: str = "") -> None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id FROM employments
                WHERE person_id = ? AND account_id = ? AND is_current = 1
                """,
                (person_id, account_id),
            ).fetchone()
            if row:
                return
            now = _utc_now()
            conn.execute(
                """
                INSERT INTO employments(
                    id, person_id, account_id, title, is_current, confidence,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, 1, 0.5, ?, ?)
                """,
                (_new_id(), person_id, account_id, title or "", now, now),
            )

    # --- leads ---

    def upsert_lead(
        self,
        *,
        account_id: str | None,
        person_id: str | None,
        source: str,
        status: str = "NEW",
        bitrix_deal_id: str | None = None,
        campaign_id: str | None = None,
        product: str | None = None,
        score: float | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        # Prefer existing open lead for same account+person+source
        with self.connect() as conn:
            row = None
            if account_id or person_id:
                row = conn.execute(
                    """
                    SELECT * FROM leads
                    WHERE tenant_id = ?
                      AND IFNULL(account_id,'') = IFNULL(?, '')
                      AND IFNULL(person_id,'') = IFNULL(?, '')
                      AND source = ?
                      AND status NOT IN ('WON','LOST','BLACKLISTED')
                    ORDER BY updated_at DESC LIMIT 1
                    """,
                    (self.tenant_id, account_id, person_id, source),
                ).fetchone()
            if row:
                lid = row["id"]
                conn.execute(
                    """
                    UPDATE leads SET
                        status = ?,
                        bitrix_deal_id = COALESCE(?, bitrix_deal_id),
                        score = COALESCE(?, score),
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (status, bitrix_deal_id, score, now, lid),
                )
            else:
                lid = _new_id()
                conn.execute(
                    """
                    INSERT INTO leads(
                        id, tenant_id, account_id, person_id, source, campaign_id,
                        product, score, status, bitrix_deal_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lid,
                        self.tenant_id,
                        account_id,
                        person_id,
                        source,
                        campaign_id,
                        product,
                        score,
                        status,
                        bitrix_deal_id,
                        now,
                        now,
                    ),
                )
        with self.connect() as conn:
            out = conn.execute("SELECT * FROM leads WHERE id = ?", (lid,)).fetchone()
        return dict(out) if out else {"id": lid}

    # --- events ---

    def emit_event(
        self,
        *,
        event_type: str,
        source: str = "",
        channel: str | None = None,
        account_id: str | None = None,
        person_id: str | None = None,
        conversation_id: str | None = None,
        campaign_id: str | None = None,
        correlation_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        now = _utc_now()
        eid = _new_id()
        idem = (idempotency_key or "").strip() or None
        with self.connect() as conn:
            if idem:
                existing = conn.execute(
                    """
                    SELECT * FROM domain_events
                    WHERE tenant_id = ? AND idempotency_key = ?
                    """,
                    (self.tenant_id, idem),
                ).fetchone()
                if existing:
                    return dict(existing)
            conn.execute(
                """
                INSERT INTO domain_events(
                    id, tenant_id, event_type, occurred_at, source, channel,
                    account_id, person_id, conversation_id, campaign_id,
                    correlation_id, idempotency_key, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    eid,
                    self.tenant_id,
                    event_type,
                    now,
                    source or "",
                    channel,
                    account_id,
                    person_id,
                    conversation_id,
                    campaign_id,
                    correlation_id,
                    idem,
                    json.dumps(payload or {}, ensure_ascii=False),
                    now,
                ),
            )
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM domain_events WHERE id = ?", (eid,)
            ).fetchone()
        return dict(row) if row else {"id": eid, "event_type": event_type}

    def list_events(
        self, *, event_type: str | None = None, limit: int = 50
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 200))
        with self.connect() as conn:
            if event_type:
                rows = conn.execute(
                    """
                    SELECT * FROM domain_events
                    WHERE tenant_id = ? AND event_type = ?
                    ORDER BY occurred_at DESC LIMIT ?
                    """,
                    (self.tenant_id, event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM domain_events WHERE tenant_id = ?
                    ORDER BY occurred_at DESC LIMIT ?
                    """,
                    (self.tenant_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def timeline(self, account_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return [
            e
            for e in self.list_events(limit=limit * 2)
            if e.get("account_id") == account_id
        ][:limit]

    # --- resolve helpers (Slice A) ---

    def resolve_inbound(
        self,
        *,
        email: str | None = None,
        bitrix_company_id: str | None = None,
        contact_name: str = "",
        company_title: str = "",
        phone: str | None = None,
        classification: str | None = None,
        bitrix_deal_id: str | None = None,
        source: str = "email_reply",
    ) -> dict[str, Any]:
        """Resolve/create Account+Person+Lead for an inbound signal."""
        account = None
        if bitrix_company_id:
            account = self.get_account_by_bitrix(bitrix_company_id)
            if not account:
                account = self.upsert_account_from_company(
                    {
                        "bitrix_id": bitrix_company_id,
                        "title": company_title or f"Company {bitrix_company_id}",
                    }
                )
            else:
                # refresh name if empty
                if company_title and not (account.get("legal_name") or "").strip():
                    account = self.upsert_account_from_company(
                        {
                            "bitrix_id": bitrix_company_id,
                            "title": company_title,
                        }
                    )

        person = self.ensure_person(
            full_name=contact_name,
            email=email,
            phone=phone,
            account_id=account["id"] if account else None,
        )

        lead_status = "NEW"
        if classification in ("positive_interest", "forwarded"):
            lead_status = "INTERESTED"
        elif classification in ("human_unclassified", "negative"):
            lead_status = "REPLIED"
        elif classification == "unsubscribe":
            lead_status = "BLACKLISTED"

        if account:
            if lead_status == "BLACKLISTED":
                self.set_lifecycle(account["id"], "BLACKLISTED")
            elif lead_status == "INTERESTED":
                self.set_lifecycle(account["id"], "INTERESTED")
            elif lead_status == "REPLIED":
                cur = account.get("lifecycle_status") or "NEW"
                if cur not in ("BLACKLISTED", "DISQUALIFIED", "MEETING_BOOKED", "INTERESTED"):
                    self.set_lifecycle(account["id"], "REPLIED")
            account = self.get_account(account["id"]) or account

        lead = self.upsert_lead(
            account_id=account["id"] if account else None,
            person_id=person["id"],
            source=source,
            status=lead_status,
            bitrix_deal_id=bitrix_deal_id,
            score=0.8 if lead_status == "INTERESTED" else 0.5,
        )
        return {
            "ok": True,
            "account": account,
            "person": person,
            "lead": lead,
        }

    def latest_lead(
        self,
        *,
        account_id: str | None = None,
        person_id: str | None = None,
    ) -> dict[str, Any] | None:
        if not account_id and not person_id:
            return None
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM leads
                WHERE tenant_id = ?
                  AND (? IS NULL OR account_id = ?)
                  AND (? IS NULL OR person_id = ?)
                ORDER BY updated_at DESC LIMIT 1
                """,
                (
                    self.tenant_id,
                    account_id,
                    account_id,
                    person_id,
                    person_id,
                ),
            ).fetchone()
        return dict(row) if row else None

    def enrichment_context(
        self,
        *,
        email: str | None = None,
        bitrix_company_id: str | None = None,
        classification: str | None = None,
        contact_name: str = "",
        company_title: str = "",
        create_if_missing: bool = False,
    ) -> dict[str, Any]:
        """Lookup Account/Person/Lead for inbox enrichment panel (read-mostly)."""
        account = None
        person = None
        if bitrix_company_id:
            account = self.get_account_by_bitrix(bitrix_company_id)
        if email:
            person = self.find_person_by_email(email)

        if create_if_missing and (email or bitrix_company_id):
            resolved = self.resolve_inbound(
                email=email,
                bitrix_company_id=bitrix_company_id,
                contact_name=contact_name,
                company_title=company_title,
                classification=classification,
                source="inbox_enrichment",
            )
            account = resolved.get("account") or account
            person = resolved.get("person") or person
            lead = resolved.get("lead")
        else:
            lead = self.latest_lead(
                account_id=account["id"] if account else None,
                person_id=person["id"] if person else None,
            )

        lifecycle = (account or {}).get("lifecycle_status")
        lead_status = (lead or {}).get("status")
        next_action = suggest_next_action(
            lifecycle=lifecycle,
            lead_status=lead_status,
            classification=classification,
        )
        draft = suggested_reply_draft(
            classification=classification,
            account_name=(account or {}).get("legal_name")
            or (account or {}).get("brand_name")
            or company_title
            or "",
            person_name=(person or {}).get("full_name") or contact_name or "",
            next_action=next_action,
        )
        return {
            "ok": True,
            "account": account,
            "person": person,
            "lead": lead,
            "next_action": next_action,
            "suggested_reply": draft,
        }

    def sync_from_clients(self, *, limit: int = 500) -> dict[str, Any]:
        """Backfill accounts from clients.companies."""
        from modules.clients import ClientsStore

        clients = ClientsStore()
        n = 0
        with clients.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM companies ORDER BY updated_at DESC LIMIT ?",
                (max(1, min(limit, 5000)),),
            ).fetchall()
        for r in rows:
            self.upsert_account_from_company(dict(r))
            n += 1
        return {"ok": True, "upserted": n}


def suggest_next_action(
    *,
    lifecycle: str | None = None,
    lead_status: str | None = None,
    classification: str | None = None,
) -> dict[str, Any]:
    """Rules-first next action for Slice A (no LLM)."""
    cls = (classification or "").strip().lower()
    life = (lifecycle or lead_status or "NEW").strip().upper()

    if cls == "unsubscribe" or life == "BLACKLISTED":
        return {
            "action": "suppress",
            "label": "Не писать — suppress / BLACKLISTED",
            "priority": "high",
            "channel": None,
            "reason": "unsubscribe_or_blacklist",
        }
    if cls == "positive_interest" or life == "INTERESTED":
        return {
            "action": "propose_meeting",
            "label": "Предложить слот / ответить с CTA встречи",
            "priority": "high",
            "channel": "email",
            "reason": "positive_interest",
        }
    if cls == "forwarded":
        return {
            "action": "follow_cc",
            "label": "Уточнить ЛПР у того, кому переслали",
            "priority": "medium",
            "channel": "email",
            "reason": "forwarded",
        }
    if cls == "negative":
        return {
            "action": "close_politely",
            "label": "Вежливо закрыть + пауза последовательности",
            "priority": "medium",
            "channel": "email",
            "reason": "negative",
        }
    if life == "MEETING_BOOKED":
        return {
            "action": "prepare_meeting",
            "label": "Подтвердить встречу / бриф",
            "priority": "high",
            "channel": "email",
            "reason": "meeting_booked",
        }
    if cls == "human_unclassified" or life == "REPLIED":
        return {
            "action": "operator_reply",
            "label": "Ответить оператором из Inbox",
            "priority": "high",
            "channel": "email",
            "reason": "needs_human_reply",
        }
    return {
        "action": "review",
        "label": "Просмотреть карточку Account",
        "priority": "low",
        "channel": None,
        "reason": "default",
    }


def suggested_reply_draft(
    *,
    classification: str | None,
    account_name: str = "",
    person_name: str = "",
    next_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stub reply draft — APPROVAL_REQUIRED; SB citations filled later."""
    action = (next_action or {}).get("action") or "review"
    name = (person_name or "").strip() or "коллеги"
    company = (account_name or "").strip()
    company_bit = f" ({company})" if company else ""

    bodies = {
        "propose_meeting": (
            f"Здравствуйте, {name}!\n\n"
            f"Спасибо за ответ{company_bit}. Готовы коротко созвониться "
            "и показать, как Quantum Labs закрывает ваш кейс. "
            "Удобны ли вам 2–3 слота на этой неделе?\n\n"
            "С уважением,\nQuantum Labs"
        ),
        "close_politely": (
            f"Здравствуйте, {name}!\n\n"
            "Понял, спасибо за ответ. Не буду беспокоить. "
            "Если тема станет актуальной — напишите, будем рады помочь.\n\n"
            "С уважением,\nQuantum Labs"
        ),
        "follow_cc": (
            f"Здравствуйте, {name}!\n\n"
            "Вижу, письмо переслали коллеге. Подскажите, пожалуйста, "
            "с кем лучше продолжить диалог по внедрению?\n\n"
            "С уважением,\nQuantum Labs"
        ),
        "operator_reply": (
            f"Здравствуйте, {name}!\n\n"
            f"Спасибо за сообщение{company_bit}. "
            "[уточните ответ по сути запроса]\n\n"
            "С уважением,\nQuantum Labs"
        ),
        "suppress": "",
        "prepare_meeting": (
            f"Здравствуйте, {name}!\n\n"
            "Напоминаю о нашей встрече. Если нужно перенести слот — "
            "напишите, подберём другое время.\n\n"
            "С уважением,\nQuantum Labs"
        ),
    }
    body = bodies.get(action, bodies["operator_reply"])
    return {
        "approval_required": True,
        "status": "draft",
        "action": action,
        "body": body,
        "citations": [
            {
                "source": "tenant_config",
                "ref": "config/tenants/quantum-labs/product_profile.json",
                "note": "Second Brain claim cite — Stage 2 wiring",
            }
        ],
        "classification": classification,
    }


def classify_to_lifecycle(classification: str | None) -> str | None:
    mapping = {
        "positive_interest": "INTERESTED",
        "human_unclassified": "REPLIED",
        "forwarded": "INTERESTED",
        "negative": "REPLIED",
        "unsubscribe": "BLACKLISTED",
    }
    return mapping.get(classification or "")


class AccountsModule:
    name = "accounts"
    version = "0.1.0"

    def __init__(self) -> None:
        self.store = AccountStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["accounts"] = self.store
        logger.info("accounts module ready tenant=%s", self.store.tenant_id)

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        with self.store.connect() as conn:
            n_acc = conn.execute(
                "SELECT COUNT(*) AS n FROM accounts WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            n_people = conn.execute(
                "SELECT COUNT(*) AS n FROM people WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            n_leads = conn.execute(
                "SELECT COUNT(*) AS n FROM leads WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
            n_events = conn.execute(
                "SELECT COUNT(*) AS n FROM domain_events WHERE tenant_id = ?",
                (self.store.tenant_id,),
            ).fetchone()["n"]
        return {
            "ok": True,
            "tenant_id": self.store.tenant_id,
            "accounts": int(n_acc),
            "people": int(n_people),
            "leads": int(n_leads),
            "events": int(n_events),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query
        from pydantic import BaseModel, Field

        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("")
        def list_accounts(
            q: str | None = None, limit: int = Query(50, ge=1, le=200)
        ) -> dict[str, Any]:
            return {"ok": True, "items": self.store.list_accounts(q=q, limit=limit)}

        @router.get("/meta/events")
        def events(
            event_type: str | None = None, limit: int = Query(50, ge=1, le=200)
        ) -> dict[str, Any]:
            return {
                "ok": True,
                "items": self.store.list_events(event_type=event_type, limit=limit),
            }

        @router.get("/meta/leads")
        def leads(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
            with self.store.connect() as conn:
                rows = conn.execute(
                    """
                    SELECT * FROM leads WHERE tenant_id = ?
                    ORDER BY updated_at DESC LIMIT ?
                    """,
                    (self.store.tenant_id, limit),
                ).fetchall()
            return {"ok": True, "items": [dict(r) for r in rows]}

        @router.get("/meta/enrichment")
        def enrichment(
            email: str | None = None,
            bitrix_company_id: str | None = None,
            classification: str | None = None,
            contact_name: str = "",
            company_title: str = "",
            create_if_missing: bool = False,
        ) -> dict[str, Any]:
            return self.store.enrichment_context(
                email=email,
                bitrix_company_id=bitrix_company_id,
                classification=classification,
                contact_name=contact_name,
                company_title=company_title,
                create_if_missing=create_if_missing,
            )

        @router.get("/meta/suggest-next")
        def suggest_next(
            classification: str | None = None,
            lifecycle: str | None = None,
            lead_status: str | None = None,
        ) -> dict[str, Any]:
            action = suggest_next_action(
                lifecycle=lifecycle,
                lead_status=lead_status,
                classification=classification,
            )
            return {"ok": True, "next_action": action}

        @router.get("/by-bitrix/{bitrix_id}")
        def by_bitrix(bitrix_id: str) -> dict[str, Any]:
            acc = self.store.get_account_by_bitrix(bitrix_id)
            if not acc:
                raise HTTPException(404, "account_not_found")
            return {"ok": True, "account": acc}

        @router.post("/sync-from-clients")
        def sync(limit: int = Query(500, ge=1, le=5000)) -> dict[str, Any]:
            return self.store.sync_from_clients(limit=limit)

        class ResolveBody(BaseModel):
            email: str | None = None
            phone: str | None = None
            bitrix_company_id: str | None = None
            contact_name: str = ""
            company_title: str = ""
            classification: str | None = None
            bitrix_deal_id: str | None = None
            source: str = "inbound"
            emit_event_type: str | None = Field(
                default="message.received",
                description="domain event type to emit; null to skip",
            )
            idempotency_key: str | None = None
            channel: str | None = "email"
            payload: dict[str, Any] | None = None

        @router.post("/resolve-inbound")
        def resolve_inbound(body: ResolveBody) -> dict[str, Any]:
            out = self.store.resolve_inbound(
                email=body.email,
                bitrix_company_id=body.bitrix_company_id,
                contact_name=body.contact_name,
                company_title=body.company_title,
                phone=body.phone,
                classification=body.classification,
                bitrix_deal_id=body.bitrix_deal_id,
                source=body.source,
            )
            if body.emit_event_type:
                ev = self.store.emit_event(
                    event_type=body.emit_event_type,
                    source="api",
                    channel=body.channel,
                    account_id=(out.get("account") or {}).get("id"),
                    person_id=(out.get("person") or {}).get("id"),
                    idempotency_key=body.idempotency_key,
                    payload=body.payload
                    or {
                        "email": body.email,
                        "phone": body.phone,
                        "classification": body.classification,
                        "source": body.source,
                    },
                )
                out["event"] = ev
            return out

        @router.get("/{account_id}")
        def get_account(account_id: str) -> dict[str, Any]:
            if account_id in {"meta", "health", "by-bitrix", "sync-from-clients"}:
                raise HTTPException(404, "not_found")
            acc = self.store.get_account(account_id)
            if not acc:
                raise HTTPException(404, "account_not_found")
            return {
                "ok": True,
                "account": acc,
                "timeline": self.store.timeline(account_id, limit=30),
            }

        class LifecycleBody(BaseModel):
            status: str = Field(..., min_length=2, max_length=40)

        @router.post("/{account_id}/lifecycle")
        def set_lifecycle(account_id: str, body: LifecycleBody) -> dict[str, Any]:
            try:
                acc = self.store.set_lifecycle(account_id, body.status)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            if not acc:
                raise HTTPException(404, "account_not_found")
            return {"ok": True, "account": acc}
