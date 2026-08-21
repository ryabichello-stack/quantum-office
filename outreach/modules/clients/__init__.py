"""Local clients mirror of Bitrix CRM (independent of outbox / sending).

Stored in data/clients.db so outreach can keep working if Bitrix is down.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from bitrix_client import (
    OWNER_COMPANY,
    BitrixClient,
    company_display_name,
    contact_display_name,
    extract_emails_from_fields,
    normalize_email,
)
from core.paths import DATA_DIR
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.clients")

CLIENTS_DB = DATA_DIR / "clients.db"

_PHONE_RE = re.compile(r"[+\d][\d\s\-()]{5,}\d")


def extract_phones_from_fields(fields: dict[str, Any]) -> list[str]:
    phones: list[str] = []
    seen: set[str] = set()
    for key in ("PHONE", "phone", "UF_PHONE"):
        if key not in fields:
            continue
        raw = fields[key]
        items = raw if isinstance(raw, list) else [raw]
        for item in items:
            if isinstance(item, dict):
                val = str(item.get("VALUE") or item.get("value") or "").strip()
            else:
                val = str(item or "").strip()
            if not val:
                continue
            # normalize spaces
            compact = re.sub(r"\s+", " ", val)
            if compact not in seen:
                seen.add(compact)
                phones.append(compact)
    return phones


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ClientsStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or CLIENTS_DB)
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
                CREATE TABLE IF NOT EXISTS companies (
                    bitrix_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL DEFAULT '',
                    emails_json TEXT NOT NULL DEFAULT '[]',
                    phones_json TEXT NOT NULL DEFAULT '[]',
                    primary_email TEXT,
                    date_create TEXT,
                    raw_json TEXT,
                    synced_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
            if "inn" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN inn TEXT")
            if "ogrn" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN ogrn TEXT")
            if "requisites_json" not in cols:
                conn.execute(
                    "ALTER TABLE companies ADD COLUMN requisites_json TEXT NOT NULL DEFAULT '[]'"
                )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS contacts (
                    bitrix_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL DEFAULT '',
                    last_name TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    company_bitrix_id TEXT NOT NULL DEFAULT '',
                    emails_json TEXT NOT NULL DEFAULT '[]',
                    phones_json TEXT NOT NULL DEFAULT '[]',
                    primary_email TEXT,
                    post TEXT,
                    date_create TEXT,
                    raw_json TEXT,
                    synced_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS requisites (
                    bitrix_id TEXT PRIMARY KEY,
                    entity_type_id TEXT NOT NULL DEFAULT '',
                    entity_bitrix_id TEXT NOT NULL DEFAULT '',
                    inn TEXT,
                    ogrn TEXT,
                    company_name TEXT,
                    director TEXT,
                    raw_json TEXT NOT NULL DEFAULT '{}',
                    synced_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS client_emails (
                    email TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    bitrix_id TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    company_bitrix_id TEXT NOT NULL DEFAULT '',
                    active INTEGER NOT NULL DEFAULT 1,
                    synced_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sync_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    ok INTEGER,
                    report_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_client_emails_active ON client_emails(active)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_companies_email ON companies(primary_email)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_contacts_email ON contacts(primary_email)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_companies_inn ON companies(inn)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_requisites_entity "
                "ON requisites(entity_type_id, entity_bitrix_id)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_requisites_inn ON requisites(inn)"
            )

    def upsert_company(
        self,
        company: dict[str, Any],
        *,
        requisites: list[dict[str, Any]] | None = None,
    ) -> None:
        now = _utc_now()
        bid = str(company.get("ID") or "").strip()
        if not bid:
            return
        emails = extract_emails_from_fields(company)
        phones = extract_phones_from_fields(company)
        title = company_display_name(company)
        primary = emails[0] if emails else None
        reqs = requisites if requisites is not None else []
        inn = None
        ogrn = None
        for rq in reqs:
            if not inn:
                inn = str(rq.get("RQ_INN") or "").strip() or None
            if not ogrn:
                ogrn = (
                    str(rq.get("RQ_OGRN") or rq.get("RQ_OGRNIP") or "").strip() or None
                )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO companies(
                    bitrix_id, title, emails_json, phones_json, primary_email,
                    date_create, raw_json, synced_at, updated_at,
                    inn, ogrn, requisites_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bitrix_id) DO UPDATE SET
                    title=excluded.title,
                    emails_json=excluded.emails_json,
                    phones_json=excluded.phones_json,
                    primary_email=excluded.primary_email,
                    date_create=excluded.date_create,
                    raw_json=excluded.raw_json,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at,
                    inn=COALESCE(excluded.inn, companies.inn),
                    ogrn=COALESCE(excluded.ogrn, companies.ogrn),
                    requisites_json=excluded.requisites_json
                """,
                (
                    bid,
                    title,
                    json.dumps(emails, ensure_ascii=False),
                    json.dumps(phones, ensure_ascii=False),
                    primary,
                    company.get("DATE_CREATE"),
                    json.dumps(company, ensure_ascii=False),
                    now,
                    now,
                    inn,
                    ogrn,
                    json.dumps(reqs, ensure_ascii=False),
                ),
            )
            for email in emails:
                conn.execute(
                    """
                    INSERT INTO client_emails(
                        email, source, bitrix_id, display_name, company_bitrix_id, active, synced_at
                    ) VALUES (?, 'company', ?, ?, ?, 1, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        source=excluded.source,
                        bitrix_id=excluded.bitrix_id,
                        display_name=excluded.display_name,
                        company_bitrix_id=excluded.company_bitrix_id,
                        active=1,
                        synced_at=excluded.synced_at
                    """,
                    (email, bid, title, bid, now),
                )

    def upsert_requisite(self, requisite: dict[str, Any]) -> None:
        now = _utc_now()
        rid = str(requisite.get("ID") or "").strip()
        if not rid:
            return
        entity_type = str(requisite.get("ENTITY_TYPE_ID") or "").strip()
        entity_id = str(requisite.get("ENTITY_ID") or "").strip()
        inn = str(requisite.get("RQ_INN") or "").strip() or None
        ogrn = (
            str(requisite.get("RQ_OGRN") or requisite.get("RQ_OGRNIP") or "").strip()
            or None
        )
        company_name = (
            str(
                requisite.get("RQ_COMPANY_NAME")
                or requisite.get("RQ_COMPANY_FULL_NAME")
                or ""
            ).strip()
            or None
        )
        director = (
            str(
                requisite.get("RQ_DIRECTOR")
                or requisite.get("RQ_CEO_NAME")
                or requisite.get("RQ_NAME")
                or ""
            ).strip()
            or None
        )
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO requisites(
                    bitrix_id, entity_type_id, entity_bitrix_id, inn, ogrn,
                    company_name, director, raw_json, synced_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bitrix_id) DO UPDATE SET
                    entity_type_id=excluded.entity_type_id,
                    entity_bitrix_id=excluded.entity_bitrix_id,
                    inn=excluded.inn,
                    ogrn=excluded.ogrn,
                    company_name=excluded.company_name,
                    director=excluded.director,
                    raw_json=excluded.raw_json,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at
                """,
                (
                    rid,
                    entity_type,
                    entity_id,
                    inn,
                    ogrn,
                    company_name,
                    director,
                    json.dumps(requisite, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            # Attach INN/OGRN onto company row when ENTITY_TYPE_ID = company (4)
            if entity_type == str(OWNER_COMPANY) and entity_id and inn:
                conn.execute(
                    """
                    UPDATE companies
                    SET inn = COALESCE(?, inn),
                        ogrn = COALESCE(?, ogrn),
                        updated_at = ?
                    WHERE bitrix_id = ?
                    """,
                    (inn, ogrn, now, entity_id),
                )

    def upsert_contact(self, contact: dict[str, Any]) -> None:
        now = _utc_now()
        bid = str(contact.get("ID") or "").strip()
        if not bid:
            return
        emails = extract_emails_from_fields(contact)
        phones = extract_phones_from_fields(contact)
        display = contact_display_name(contact)
        company_id = str(contact.get("COMPANY_ID") or "").strip()
        primary = emails[0] if emails else None
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO contacts(
                    bitrix_id, name, last_name, display_name, company_bitrix_id,
                    emails_json, phones_json, primary_email, post, date_create,
                    raw_json, synced_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bitrix_id) DO UPDATE SET
                    name=excluded.name,
                    last_name=excluded.last_name,
                    display_name=excluded.display_name,
                    company_bitrix_id=excluded.company_bitrix_id,
                    emails_json=excluded.emails_json,
                    phones_json=excluded.phones_json,
                    primary_email=excluded.primary_email,
                    post=excluded.post,
                    date_create=excluded.date_create,
                    raw_json=excluded.raw_json,
                    synced_at=excluded.synced_at,
                    updated_at=excluded.updated_at
                """,
                (
                    bid,
                    str(contact.get("NAME") or ""),
                    str(contact.get("LAST_NAME") or ""),
                    display,
                    company_id,
                    json.dumps(emails, ensure_ascii=False),
                    json.dumps(phones, ensure_ascii=False),
                    primary,
                    contact.get("POST"),
                    contact.get("DATE_CREATE"),
                    json.dumps(contact, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            for email in emails:
                # Prefer company mapping if email already from company; still refresh
                conn.execute(
                    """
                    INSERT INTO client_emails(
                        email, source, bitrix_id, display_name, company_bitrix_id, active, synced_at
                    ) VALUES (?, 'contact', ?, ?, ?, 1, ?)
                    ON CONFLICT(email) DO UPDATE SET
                        source=CASE
                            WHEN client_emails.source = 'company' THEN client_emails.source
                            ELSE excluded.source
                        END,
                        bitrix_id=CASE
                            WHEN client_emails.source = 'company' THEN client_emails.bitrix_id
                            ELSE excluded.bitrix_id
                        END,
                        display_name=excluded.display_name,
                        company_bitrix_id=COALESCE(
                            NULLIF(excluded.company_bitrix_id, ''),
                            client_emails.company_bitrix_id
                        ),
                        active=1,
                        synced_at=excluded.synced_at
                    """,
                    (email, bid, display, company_id, now),
                )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            companies = conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"]
            contacts = conn.execute("SELECT COUNT(*) AS n FROM contacts").fetchone()["n"]
            emails = conn.execute(
                "SELECT COUNT(*) AS n FROM client_emails WHERE active = 1"
            ).fetchone()["n"]
            requisites = conn.execute("SELECT COUNT(*) AS n FROM requisites").fetchone()["n"]
            with_inn = conn.execute(
                "SELECT COUNT(*) AS n FROM companies WHERE inn IS NOT NULL AND inn != ''"
            ).fetchone()["n"]
        return {
            "companies": int(companies),
            "contacts": int(contacts),
            "emails": int(emails),
            "requisites": int(requisites),
            "companies_with_inn": int(with_inn),
        }

    def list_emails(
        self,
        *,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        clauses: list[str] = ["active = 1"]
        params: list[Any] = []
        if q:
            clauses.append(
                "(lower(email) LIKE ? OR lower(display_name) LIKE ? OR company_bitrix_id LIKE ?)"
            )
            like = f"%{q.strip().lower()}%"
            params.extend([like, like, f"%{q.strip()}%"])
        where = " WHERE " + " AND ".join(clauses)
        with self.connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) AS n FROM client_emails{where}", params
            ).fetchone()["n"]
            rows = conn.execute(
                f"""
                SELECT * FROM client_emails{where}
                ORDER BY synced_at DESC, email ASC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], int(total)

    def iter_outreach_targets(self) -> Iterator[dict[str, Any]]:
        """Unique active emails for rebuilding outbox from local mirror."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT email, display_name, company_bitrix_id, source, bitrix_id
                FROM client_emails
                WHERE active = 1 AND email IS NOT NULL AND email != ''
                ORDER BY email ASC
                """
            ).fetchall()
        for r in rows:
            yield dict(r)

    def begin_sync_run(self) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO sync_runs(started_at, ok) VALUES (?, NULL)",
                (_utc_now(),),
            )
            return int(cur.lastrowid)

    def finish_sync_run(self, run_id: int, report: dict[str, Any]) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE sync_runs
                SET finished_at = ?, ok = ?, report_json = ?
                WHERE id = ?
                """,
                (
                    _utc_now(),
                    1 if report.get("ok") else 0,
                    json.dumps(report, ensure_ascii=False),
                    run_id,
                ),
            )

    def last_sync(self) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        if out.get("report_json"):
            try:
                out["report"] = json.loads(out["report_json"])
            except json.JSONDecodeError:
                out["report"] = None
        return out


def sync_from_bitrix(store: ClientsStore, client: BitrixClient) -> dict[str, Any]:
    """Full Bitrix pull: all company/contact fields + all requisites (INN etc.)."""
    run_id = store.begin_sync_run()
    companies_n = 0
    contacts_n = 0
    requisites_n = 0
    company_emails = 0
    contact_emails = 0
    company_field_keys: set[str] = set()
    contact_field_keys: set[str] = set()
    requisite_field_keys: set[str] = set()
    try:
        # 1) Requisites first so company upsert can attach INN in the same pass
        reqs_by_company: dict[str, list[dict[str, Any]]] = {}
        for rq in client.list_requisites():
            store.upsert_requisite(rq)
            requisites_n += 1
            requisite_field_keys.update(rq.keys())
            if str(rq.get("ENTITY_TYPE_ID") or "") == str(OWNER_COMPANY):
                eid = str(rq.get("ENTITY_ID") or "").strip()
                if eid:
                    reqs_by_company.setdefault(eid, []).append(rq)

        for company in client.list_companies():
            bid = str(company.get("ID") or "").strip()
            store.upsert_company(company, requisites=reqs_by_company.get(bid) or [])
            companies_n += 1
            company_emails += len(extract_emails_from_fields(company))
            company_field_keys.update(company.keys())

        for contact in client.list_contacts():
            store.upsert_contact(contact)
            contacts_n += 1
            contact_emails += len(extract_emails_from_fields(contact))
            contact_field_keys.update(contact.keys())

        # After companies exist, re-apply INN from requisites (covers order edge cases)
        for eid, reqs in reqs_by_company.items():
            for rq in reqs:
                store.upsert_requisite(rq)

        report = {
            "ok": True,
            "companies_synced": companies_n,
            "contacts_synced": contacts_n,
            "requisites_synced": requisites_n,
            "company_email_fields": company_emails,
            "contact_email_fields": contact_emails,
            "company_fields_seen": sorted(company_field_keys),
            "contact_fields_seen": sorted(contact_field_keys),
            "requisite_fields_seen": sorted(requisite_field_keys),
            "company_fields_count": len(company_field_keys),
            "contact_fields_count": len(contact_field_keys),
            "requisite_fields_count": len(requisite_field_keys),
            "counts": store.counts(),
            "db_path": str(store.db_path),
            "note": (
                "select=['*','UF_*','EMAIL','PHONE','WEB','IM'] for companies/contacts; "
                "requisites via crm.requisite.list select=['*'] (RQ_INN etc.)"
            ),
        }
        store.finish_sync_run(run_id, report)
        logger.info(
            "clients sync done companies=%s contacts=%s requisites=%s with_inn=%s fields_c=%s",
            companies_n,
            contacts_n,
            requisites_n,
            report["counts"].get("companies_with_inn"),
            report["company_fields_count"],
        )
        return report
    except Exception as exc:  # noqa: BLE001
        report = {"ok": False, "error": str(exc)[:500], "counts": store.counts()}
        store.finish_sync_run(run_id, report)
        logger.exception("clients sync failed")
        return report


def rebuild_outbox_from_clients(clients: ClientsStore, outbox: Any) -> dict[str, Any]:
    """Push local client emails into outbox (pending), without Bitrix online.

    Prefer director FIO for greeting when DaData/Bitrix enriched it.
    """
    inserted = 0
    known = 0
    with_director = 0
    for row in clients.iter_outreach_targets():
        email = normalize_email(row.get("email"))
        if not email:
            continue
        company_id = str(row.get("company_bitrix_id") or "")
        if row.get("source") == "company":
            company_id = str(row.get("bitrix_id") or company_id)
        title = str(row.get("display_name") or email)
        director = ""
        if company_id:
            try:
                with clients.connect() as conn:
                    # companies.director from Bitrix requisites; director_name from DaData enrich
                    cols = {
                        r[1]
                        for r in conn.execute("PRAGMA table_info(companies)").fetchall()
                    }
                    if "director_name" in cols or "director" in cols:
                        sel = []
                        if "director_name" in cols:
                            sel.append("director_name")
                        if "director" in cols:
                            sel.append("director")
                        q = f"SELECT {', '.join(sel)} FROM companies WHERE bitrix_id = ? LIMIT 1"
                        crow = conn.execute(q, (company_id,)).fetchone()
                        if crow:
                            for i in range(len(sel)):
                                val = str(crow[i] or "").strip()
                                if val:
                                    director = val
                                    break
            except Exception:  # noqa: BLE001
                director = ""
        person = director or (
            title
            if row.get("source") == "contact"
            else ""
        )
        greeting_name = person or title
        if director:
            with_director += 1
        if outbox.upsert_company(
            email=email, company_id=company_id or "", company_title=greeting_name
        ):
            inserted += 1
        else:
            known += 1
    return {
        "ok": True,
        "inserted_new": inserted,
        "already_known": known,
        "with_director_name": with_director,
        "outbox": outbox.counts(),
        "clients": clients.counts(),
    }


class ClientsModule:
    name = "clients"
    version = "1.1.0"

    def __init__(self) -> None:
        self.store = ClientsStore()

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        ctx.extras["clients"] = self.store
        logger.info("clients module ready %s", self.store.counts())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, **self.store.counts(), "last_sync": self.store.last_sync()}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query

        @router.get("/status")
        def status() -> dict[str, Any]:
            return {
                "ok": True,
                "counts": self.store.counts(),
                "db_path": str(self.store.db_path),
                "last_sync": self.store.last_sync(),
            }

        @router.get("/emails")
        def emails(
            q: str | None = None,
            limit: int = Query(default=50, ge=1, le=200),
            offset: int = Query(default=0, ge=0),
        ) -> dict[str, Any]:
            items, total = self.store.list_emails(q=q, limit=limit, offset=offset)
            return {"ok": True, "total": total, "items": items}
