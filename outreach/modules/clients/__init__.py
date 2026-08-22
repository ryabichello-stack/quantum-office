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
from core.paths import DATA_DIR, MODULES_DB
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
            for col, decl in (
                ("director_name", "TEXT"),
                ("dadata_json", "TEXT"),
                ("dadata_fetched_at", "TEXT"),
                ("bitrix_pushed_at", "TEXT"),
                ("city", "TEXT"),
                ("region", "TEXT"),
                ("address_line", "TEXT"),
                ("timezone_raw", "TEXT"),
                ("timezone", "TEXT"),
                ("director_first", "TEXT"),
                ("director_patronymic", "TEXT"),
                ("director_greeting", "TEXT"),
            ):
                if col not in cols:
                    conn.execute(f"ALTER TABLE companies ADD COLUMN {col} {decl}")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_companies_timezone ON companies(timezone)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_companies_city ON companies(city)"
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

    def get_company(self, bitrix_id: str) -> dict[str, Any] | None:
        cid = (bitrix_id or "").strip()
        if not cid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM companies WHERE bitrix_id = ? LIMIT 1",
                (cid,),
            ).fetchone()
        return dict(row) if row else None

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


def company_geo_row(clients: ClientsStore, company_id: str) -> dict[str, Any]:
    """Lookup persisted geo / director greeting for a Bitrix company id."""
    cid = str(company_id or "").strip()
    if not cid:
        return {}
    with clients.connect() as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
        want = [
            "city",
            "region",
            "address_line",
            "timezone_raw",
            "timezone",
            "director_name",
            "director_first",
            "director_patronymic",
            "director_greeting",
        ]
        sel = [c for c in want if c in cols]
        if not sel:
            return {}
        row = conn.execute(
            f"SELECT {', '.join(sel)} FROM companies WHERE bitrix_id = ? LIMIT 1",
            (cid,),
        ).fetchone()
    if not row:
        return {}
    return {k: (str(row[k]).strip() if row[k] is not None else "") for k in sel}


def backfill_company_geo_and_fio(
    clients: ClientsStore,
    *,
    dadata_db: Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Fill city/timezone + director first/patronymic from DaData cache / Bitrix raw."""
    from geo_schedule import (
        extract_geo_from_bitrix_company,
        extract_geo_from_dadata_raw,
        iana_from_utc_offset,
        split_russian_fio,
    )

    clients.init_db()
    dadata_path = Path(dadata_db or MODULES_DB)
    updated = 0
    with_tz = 0
    with_city = 0
    with_greeting = 0
    scanned = 0

    dadata_by_inn: dict[str, dict[str, Any]] = {}
    if dadata_path.exists():
        dconn = sqlite3.connect(dadata_path)
        dconn.row_factory = sqlite3.Row
        try:
            for r in dconn.execute(
                "SELECT inn, director_name, address, raw_json FROM dadata_parties"
            ):
                try:
                    raw = json.loads(r["raw_json"] or "{}")
                except json.JSONDecodeError:
                    raw = {}
                dadata_by_inn[str(r["inn"])] = {
                    "director_name": r["director_name"],
                    "address": r["address"],
                    "raw": raw,
                }
        finally:
            dconn.close()

    with clients.connect() as conn:
        rows = conn.execute(
            """
            SELECT bitrix_id, inn, director_name, raw_json, dadata_json
            FROM companies
            ORDER BY bitrix_id ASC
            """
        ).fetchall()
        if limit is not None:
            rows = rows[: max(0, int(limit))]

        for row in rows:
            scanned += 1
            cid = str(row["bitrix_id"])
            inn = str(row["inn"] or "").strip()
            director = str(row["director_name"] or "").strip()
            geo: dict[str, str] = {}
            party = dadata_by_inn.get(inn) if inn else None
            if party:
                geo.update(extract_geo_from_dadata_raw(party.get("raw")))
                if not director:
                    director = str(party.get("director_name") or "").strip()
            try:
                bitrix_raw = json.loads(row["raw_json"] or "{}")
            except json.JSONDecodeError:
                bitrix_raw = {}
            bitrix_geo = extract_geo_from_bitrix_company(bitrix_raw)
            for k, v in bitrix_geo.items():
                geo.setdefault(k, v)

            if geo.get("timezone_raw") and not geo.get("timezone"):
                geo["timezone"] = iana_from_utc_offset(geo["timezone_raw"])

            fio = split_russian_fio(director)
            greeting = fio.greeting
            conn.execute(
                """
                UPDATE companies SET
                    city = COALESCE(NULLIF(?, ''), city),
                    region = COALESCE(NULLIF(?, ''), region),
                    address_line = COALESCE(NULLIF(?, ''), address_line),
                    timezone_raw = COALESCE(NULLIF(?, ''), timezone_raw),
                    timezone = COALESCE(NULLIF(?, ''), timezone),
                    director_name = COALESCE(NULLIF(?, ''), director_name),
                    director_first = ?,
                    director_patronymic = ?,
                    director_greeting = ?,
                    updated_at = ?
                WHERE bitrix_id = ?
                """,
                (
                    geo.get("city") or "",
                    geo.get("region") or "",
                    geo.get("address_line") or "",
                    geo.get("timezone_raw") or "",
                    geo.get("timezone") or "",
                    director,
                    fio.first or None,
                    fio.patronymic or None,
                    greeting or None,
                    _utc_now(),
                    cid,
                ),
            )
            updated += 1
            if geo.get("timezone"):
                with_tz += 1
            if geo.get("city"):
                with_city += 1
            if greeting:
                with_greeting += 1

    return {
        "ok": True,
        "scanned": scanned,
        "updated": updated,
        "with_timezone": with_tz,
        "with_city": with_city,
        "with_director_greeting": with_greeting,
        "dadata_cache": len(dadata_by_inn),
    }


def geo_stats(clients: ClientsStore) -> dict[str, Any]:
    clients.init_db()
    with clients.connect() as conn:
        total = conn.execute("SELECT COUNT(*) AS n FROM companies").fetchone()["n"]
        with_city = conn.execute(
            "SELECT COUNT(*) AS n FROM companies WHERE city IS NOT NULL AND city != ''"
        ).fetchone()["n"]
        with_tz = conn.execute(
            "SELECT COUNT(*) AS n FROM companies WHERE timezone IS NOT NULL AND timezone != ''"
        ).fetchone()["n"]
        with_greet = conn.execute(
            "SELECT COUNT(*) AS n FROM companies "
            "WHERE director_greeting IS NOT NULL AND director_greeting != ''"
        ).fetchone()["n"]
        tz_rows = conn.execute(
            """
            SELECT timezone, COUNT(*) AS n FROM companies
            WHERE timezone IS NOT NULL AND timezone != ''
            GROUP BY timezone ORDER BY n DESC
            """
        ).fetchall()
    return {
        "ok": True,
        "companies": int(total),
        "with_city": int(with_city),
        "with_timezone": int(with_tz),
        "with_director_greeting": int(with_greet),
        "timezones": {str(r["timezone"]): int(r["n"]) for r in tz_rows},
    }


def rebuild_outbox_from_clients(clients: ClientsStore, outbox: Any) -> dict[str, Any]:
    """Push local client emails into outbox (pending), without Bitrix online.

    Prefer director greeting (Имя Отчество) when enriched; else full director FIO.
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
        director_greeting = ""
        if company_id:
            try:
                with clients.connect() as conn:
                    cols = {
                        r[1]
                        for r in conn.execute("PRAGMA table_info(companies)").fetchall()
                    }
                    sel: list[str] = []
                    for c in (
                        "director_greeting",
                        "director_name",
                        "director",
                    ):
                        if c in cols:
                            sel.append(c)
                    if sel:
                        q = (
                            f"SELECT {', '.join(sel)} FROM companies "
                            "WHERE bitrix_id = ? LIMIT 1"
                        )
                        crow = conn.execute(q, (company_id,)).fetchone()
                        if crow:
                            for c in sel:
                                val = str(crow[c] or "").strip()
                                if not val:
                                    continue
                                if c == "director_greeting":
                                    director_greeting = val
                                elif not director:
                                    director = val
            except Exception:  # noqa: BLE001
                director = ""
        person = director_greeting or director or (
            title if row.get("source") == "contact" else ""
        )
        greeting_name = person or title
        if director or director_greeting:
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
            enriched: list[dict[str, Any]] = []
            for row in items:
                cid = str(row.get("company_bitrix_id") or row.get("bitrix_id") or "")
                geo = company_geo_row(self.store, cid) if cid else {}
                enriched.append(
                    {
                        **row,
                        "city": geo.get("city") or "",
                        "timezone": geo.get("timezone") or geo.get("timezone_raw") or "",
                        "director_greeting": geo.get("director_greeting") or "",
                    }
                )
            return {"ok": True, "total": total, "items": enriched}

        @router.get("/company/{company_id}")
        def company_card(company_id: str) -> dict[str, Any]:
            from company_card import build_company_card

            out = build_company_card(company_id, clients=self.store)
            if not out.get("ok"):
                raise HTTPException(
                    status_code=404,
                    detail=out.get("error") or "company_not_found",
                )
            return out
