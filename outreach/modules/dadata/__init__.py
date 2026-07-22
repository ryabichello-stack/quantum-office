"""DaData enrichment by INN (party findById) + local cache.

Any party payload from DaData is stored raw; convenience columns extract
director / name / address / OKVED for personalization.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import httpx

from core.paths import DATA_DIR, MODULES_DB
from core.registry import AppContext
from modules.clients import CLIENTS_DB, ClientsStore

logger = logging.getLogger("ava-outreach.dadata")

_INN_RE = re.compile(r"^\d{10}(\d{2})?$")
PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party"
SUGGEST_PARTY_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs/suggest/party"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_inn(value: str | None) -> str | None:
    if value is None:
        return None
    digits = re.sub(r"\D+", "", str(value))
    if _INN_RE.match(digits):
        return digits
    return None


def dadata_configured() -> bool:
    return bool((os.getenv("DADATA_API_KEY") or "").strip())


def _headers() -> dict[str, str]:
    api_key = (os.getenv("DADATA_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("DADATA_API_KEY is not set")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Token {api_key}",
    }
    secret = (os.getenv("DADATA_SECRET_KEY") or "").strip()
    if secret:
        headers["X-Secret"] = secret
    return headers


def extract_party_fields(suggestion: dict[str, Any]) -> dict[str, Any]:
    """Flatten useful fields from a DaData party suggestion."""
    data = suggestion.get("data") if isinstance(suggestion.get("data"), dict) else {}
    management = data.get("management") if isinstance(data.get("management"), dict) else {}
    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    opf = data.get("opf") if isinstance(data.get("opf"), dict) else {}
    state = data.get("state") if isinstance(data.get("state"), dict) else {}
    fio = data.get("fio") if isinstance(data.get("fio"), dict) else {}

    director = (
        str(management.get("name") or "").strip()
        or " ".join(
            p
            for p in (
                str(fio.get("surname") or "").strip(),
                str(fio.get("name") or "").strip(),
                str(fio.get("patronymic") or "").strip(),
            )
            if p
        ).strip()
        or None
    )
    director_post = str(management.get("post") or "").strip() or None

    return {
        "inn": str(data.get("inn") or "").strip() or None,
        "ogrn": str(data.get("ogrn") or data.get("ogrnip") or "").strip() or None,
        "kpp": str(data.get("kpp") or "").strip() or None,
        "okved": str(data.get("okved") or "").strip() or None,
        "okved_type": str(data.get("okved_type") or "").strip() or None,
        "company_name": (
            str(name.get("short_with_opf") or name.get("short") or "").strip()
            or str(suggestion.get("value") or "").strip()
            or None
        ),
        "company_full_name": str(name.get("full_with_opf") or name.get("full") or "").strip()
        or None,
        "director_name": director,
        "director_post": director_post,
        "address": str(address.get("unrestricted_value") or address.get("value") or "").strip()
        or None,
        "opf_short": str(opf.get("short") or "").strip() or None,
        "status": str(state.get("status") or "").strip() or None,
        "branch_type": str(data.get("branch_type") or "").strip() or None,
        "type": str(data.get("type") or "").strip() or None,  # LEGAL / INDIVIDUAL
        "value": str(suggestion.get("value") or "").strip() or None,
    }


class DaDataStore:
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
                CREATE TABLE IF NOT EXISTS dadata_parties (
                    inn TEXT PRIMARY KEY,
                    ogrn TEXT,
                    kpp TEXT,
                    company_name TEXT,
                    company_full_name TEXT,
                    director_name TEXT,
                    director_post TEXT,
                    address TEXT,
                    okved TEXT,
                    status TEXT,
                    party_type TEXT,
                    raw_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'findById'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS ix_dadata_director ON dadata_parties(director_name)"
            )

    def get(self, inn: str) -> dict[str, Any] | None:
        inn_n = normalize_inn(inn)
        if not inn_n:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM dadata_parties WHERE inn = ?", (inn_n,)
            ).fetchone()
        if not row:
            return None
        out = dict(row)
        try:
            out["raw"] = json.loads(out.pop("raw_json") or "{}")
        except json.JSONDecodeError:
            out["raw"] = None
        return out

    def upsert_from_suggestion(
        self, suggestion: dict[str, Any], *, source: str = "findById"
    ) -> dict[str, Any]:
        flat = extract_party_fields(suggestion)
        inn = normalize_inn(flat.get("inn"))
        if not inn:
            raise ValueError("DaData suggestion has no INN")
        now = _utc_now()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO dadata_parties(
                    inn, ogrn, kpp, company_name, company_full_name,
                    director_name, director_post, address, okved, status,
                    party_type, raw_json, fetched_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(inn) DO UPDATE SET
                    ogrn=excluded.ogrn,
                    kpp=excluded.kpp,
                    company_name=excluded.company_name,
                    company_full_name=excluded.company_full_name,
                    director_name=excluded.director_name,
                    director_post=excluded.director_post,
                    address=excluded.address,
                    okved=excluded.okved,
                    status=excluded.status,
                    party_type=excluded.party_type,
                    raw_json=excluded.raw_json,
                    fetched_at=excluded.fetched_at,
                    source=excluded.source
                """,
                (
                    inn,
                    flat.get("ogrn"),
                    flat.get("kpp"),
                    flat.get("company_name"),
                    flat.get("company_full_name"),
                    flat.get("director_name"),
                    flat.get("director_post"),
                    flat.get("address"),
                    flat.get("okved"),
                    flat.get("status"),
                    flat.get("type"),
                    json.dumps(suggestion, ensure_ascii=False),
                    now,
                    source,
                ),
            )
        cached = self.get(inn)
        assert cached is not None
        return cached

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM dadata_parties").fetchone()["n"]
            with_dir = conn.execute(
                "SELECT COUNT(*) AS n FROM dadata_parties "
                "WHERE director_name IS NOT NULL AND director_name != ''"
            ).fetchone()["n"]
        return {"cached": int(total), "with_director": int(with_dir)}

    def recent(self, limit: int = 30) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT inn, ogrn, company_name, director_name, director_post,
                       address, okved, status, fetched_at
                FROM dadata_parties
                ORDER BY fetched_at DESC
                LIMIT ?
                """,
                (max(1, min(200, limit)),),
            ).fetchall()
        return [dict(r) for r in rows]


class DaDataClient:
    def __init__(self, *, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def find_by_inn(self, inn: str) -> list[dict[str, Any]]:
        inn_n = normalize_inn(inn)
        if not inn_n:
            raise ValueError("INN must be 10 or 12 digits")
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(PARTY_URL, headers=_headers(), json={"query": inn_n})
            resp.raise_for_status()
            data = resp.json()
        suggestions = data.get("suggestions") if isinstance(data, dict) else None
        if not isinstance(suggestions, list):
            return []
        return [s for s in suggestions if isinstance(s, dict)]

    def suggest(self, query: str, *, count: int = 5) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                SUGGEST_PARTY_URL,
                headers=_headers(),
                json={"query": q, "count": max(1, min(20, count))},
            )
            resp.raise_for_status()
            data = resp.json()
        suggestions = data.get("suggestions") if isinstance(data, dict) else None
        if not isinstance(suggestions, list):
            return []
        return [s for s in suggestions if isinstance(s, dict)]


def build_bitrix_fields_from_suggestion(
    suggestion: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Map DaData party suggestion → (requisite_fields, company_fields)."""
    data = suggestion.get("data") if isinstance(suggestion.get("data"), dict) else {}
    management = data.get("management") if isinstance(data.get("management"), dict) else {}
    name = data.get("name") if isinstance(data.get("name"), dict) else {}
    address = data.get("address") if isinstance(data.get("address"), dict) else {}
    addr_data = address.get("data") if isinstance(address.get("data"), dict) else {}
    opf = data.get("opf") if isinstance(data.get("opf"), dict) else {}
    capital = data.get("capital") if isinstance(data.get("capital"), dict) else {}
    fio = data.get("fio") if isinstance(data.get("fio"), dict) else {}
    authorities = data.get("authorities") if isinstance(data.get("authorities"), dict) else {}
    fts = authorities.get("fts") if isinstance(authorities.get("fts"), dict) else {}

    director = str(management.get("name") or "").strip()
    if not director and fio:
        director = " ".join(
            p
            for p in (
                str(fio.get("surname") or "").strip(),
                str(fio.get("name") or "").strip(),
                str(fio.get("patronymic") or "").strip(),
            )
            if p
        ).strip()
    director_post = str(management.get("post") or "").strip()

    party_type = str(data.get("type") or "").upper()
    rq: dict[str, Any] = {}
    if director:
        rq["RQ_DIRECTOR"] = director
        rq["RQ_CEO_NAME"] = director
    if director_post:
        rq["RQ_CEO_WORK_POS"] = director_post
    short_name = str(name.get("short_with_opf") or name.get("short") or "").strip()
    full_name = str(name.get("full_with_opf") or name.get("full") or "").strip()
    if short_name:
        rq["RQ_COMPANY_NAME"] = short_name
    if full_name:
        rq["RQ_COMPANY_FULL_NAME"] = full_name
    inn = str(data.get("inn") or "").strip()
    if inn:
        rq["RQ_INN"] = inn
    kpp = str(data.get("kpp") or "").strip()
    if kpp:
        rq["RQ_KPP"] = kpp
    ogrn = str(data.get("ogrn") or "").strip()
    ogrnip = str(data.get("ogrnip") or "").strip()
    if party_type == "INDIVIDUAL":
        if ogrnip:
            rq["RQ_OGRNIP"] = ogrnip
        if director:
            rq["RQ_NAME"] = director
            # split FIO if possible
            parts = director.split()
            if len(parts) >= 1:
                rq["RQ_LAST_NAME"] = parts[0]
            if len(parts) >= 2:
                rq["RQ_FIRST_NAME"] = parts[1]
            if len(parts) >= 3:
                rq["RQ_SECOND_NAME"] = " ".join(parts[2:])
    else:
        if ogrn:
            rq["RQ_OGRN"] = ogrn
    okved = str(data.get("okved") or "").strip()
    if okved:
        rq["RQ_OKVED"] = okved
    for src, dst in (
        ("okpo", "RQ_OKPO"),
        ("oktmo", "RQ_OKTMO"),
    ):
        val = str(data.get(src) or "").strip()
        if val:
            rq[dst] = val
    ifns = str(fts.get("code") or fts.get("name") or "").strip()
    if ifns:
        rq["RQ_IFNS"] = ifns[:255]
    legal = str(opf.get("full") or opf.get("short") or "").strip()
    if legal:
        rq["RQ_LEGAL_FORM"] = legal
    if capital.get("value") is not None:
        rq["RQ_CAPITAL"] = str(capital.get("value"))
    ogrn_date = data.get("ogrn_date")
    if ogrn_date:
        try:
            ts = int(ogrn_date) / 1000.0
            rq["RQ_COMPANY_REG_DATE"] = datetime.fromtimestamp(
                ts, tz=timezone.utc
            ).strftime("%d.%m.%Y")
        except (TypeError, ValueError, OSError):
            pass

    company: dict[str, Any] = {}
    aval = str(address.get("unrestricted_value") or address.get("value") or "").strip()
    if aval:
        company["ADDRESS_LEGAL"] = aval
        company["REG_ADDRESS"] = aval
    city = str(addr_data.get("city_with_type") or addr_data.get("city") or "").strip()
    if city:
        company["ADDRESS_CITY"] = city
        company["REG_ADDRESS_CITY"] = city
    postal = str(addr_data.get("postal_code") or "").strip()
    if postal:
        company["ADDRESS_POSTAL_CODE"] = postal
        company["REG_ADDRESS_POSTAL_CODE"] = postal
    province = str(
        addr_data.get("region_with_type") or addr_data.get("region") or ""
    ).strip()
    if province:
        company["ADDRESS_PROVINCE"] = province
        company["REG_ADDRESS_PROVINCE"] = province
    country = str(addr_data.get("country") or "").strip()
    if country:
        company["ADDRESS_COUNTRY"] = country
        company["REG_ADDRESS_COUNTRY"] = country
    emp = data.get("employee_count")
    if emp not in (None, ""):
        company["EMPLOYEES"] = str(emp)

    return rq, company


def _requisite_id_for_company(clients: ClientsStore, company_bitrix_id: str) -> str | None:
    with clients.connect() as conn:
        row = conn.execute(
            """
            SELECT bitrix_id FROM requisites
            WHERE entity_type_id = '4' AND entity_bitrix_id = ?
            ORDER BY bitrix_id DESC
            LIMIT 1
            """,
            (company_bitrix_id,),
        ).fetchone()
        if not row:
            row = conn.execute(
                """
                SELECT bitrix_id FROM requisites
                WHERE entity_bitrix_id = ?
                ORDER BY bitrix_id DESC
                LIMIT 1
                """,
                (company_bitrix_id,),
            ).fetchone()
    return str(row["bitrix_id"]) if row else None


class DaDataEnricher:
    """Lookup + cache + optional write-back onto clients.companies / Bitrix."""

    def __init__(
        self,
        store: DaDataStore | None = None,
        clients: ClientsStore | None = None,
    ) -> None:
        self.store = store or DaDataStore()
        self.clients = clients or ClientsStore(CLIENTS_DB)
        self.api = DaDataClient()

    def lookup_inn(
        self,
        inn: str,
        *,
        force: bool = False,
        attach_company_id: str | None = None,
    ) -> dict[str, Any]:
        inn_n = normalize_inn(inn)
        if not inn_n:
            return {"ok": False, "error": "invalid_inn", "inn": inn}

        if not force:
            cached = self.store.get(inn_n)
            if cached:
                if attach_company_id:
                    self._attach_to_company(attach_company_id, cached)
                return {"ok": True, "cached": True, "inn": inn_n, "party": cached}

        if not dadata_configured():
            return {
                "ok": False,
                "error": "DADATA_API_KEY not configured",
                "inn": inn_n,
                "hint": "Set DADATA_API_KEY (and optional DADATA_SECRET_KEY) in /opt/ava-outreach/.env",
            }

        try:
            suggestions = self.api.find_by_inn(inn_n)
        except Exception as exc:  # noqa: BLE001
            logger.warning("dadata findById failed inn=%s: %s", inn_n, exc)
            return {"ok": False, "error": str(exc)[:400], "inn": inn_n}

        if not suggestions:
            return {"ok": False, "error": "not_found", "inn": inn_n, "suggestions": []}

        # Prefer MAIN branch / LEGAL if several
        best = suggestions[0]
        for s in suggestions:
            data = s.get("data") if isinstance(s.get("data"), dict) else {}
            if str(data.get("branch_type") or "").upper() == "MAIN":
                best = s
                break
        party = self.store.upsert_from_suggestion(best, source="findById")
        if attach_company_id:
            self._attach_to_company(attach_company_id, party)
        return {
            "ok": True,
            "cached": False,
            "inn": inn_n,
            "party": party,
            "suggestions_count": len(suggestions),
            "flat": extract_party_fields(best),
        }

    def _attach_to_company(self, company_bitrix_id: str, party: dict[str, Any]) -> None:
        """Persist enrichment snapshot onto companies row if present."""
        cid = str(company_bitrix_id or "").strip()
        if not cid:
            return
        now = _utc_now()
        enrich = {
            "inn": party.get("inn"),
            "ogrn": party.get("ogrn"),
            "director_name": party.get("director_name"),
            "director_post": party.get("director_post"),
            "company_name": party.get("company_name"),
            "company_full_name": party.get("company_full_name"),
            "address": party.get("address"),
            "okved": party.get("okved"),
            "status": party.get("status"),
            "fetched_at": party.get("fetched_at"),
        }
        with self.clients.connect() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
            if "dadata_json" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN dadata_json TEXT")
            if "director_name" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN director_name TEXT")
            if "dadata_fetched_at" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN dadata_fetched_at TEXT")
            conn.execute(
                """
                UPDATE companies
                SET inn = COALESCE(?, inn),
                    ogrn = COALESCE(?, ogrn),
                    director_name = ?,
                    dadata_json = ?,
                    dadata_fetched_at = ?,
                    updated_at = ?
                WHERE bitrix_id = ?
                """,
                (
                    enrich.get("inn"),
                    enrich.get("ogrn"),
                    enrich.get("director_name"),
                    json.dumps(enrich, ensure_ascii=False),
                    now,
                    now,
                    cid,
                ),
            )

    def enrich_companies(
        self,
        *,
        limit: int = 50,
        force: bool = False,
        only_missing_director: bool = True,
    ) -> dict[str, Any]:
        limit = max(1, min(500, int(limit)))
        with self.clients.connect() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
            if "director_name" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN director_name TEXT")
            if only_missing_director and not force:
                rows = conn.execute(
                    """
                    SELECT bitrix_id, inn, title FROM companies
                    WHERE inn IS NOT NULL AND inn != ''
                      AND (director_name IS NULL OR director_name = '')
                    ORDER BY bitrix_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT bitrix_id, inn, title FROM companies
                    WHERE inn IS NOT NULL AND inn != ''
                    ORDER BY bitrix_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        ok_n = 0
        fail_n = 0
        cached_n = 0
        errors: list[dict[str, Any]] = []
        for row in rows:
            res = self.lookup_inn(
                row["inn"],
                force=force,
                attach_company_id=str(row["bitrix_id"]),
            )
            if res.get("ok"):
                ok_n += 1
                if res.get("cached"):
                    cached_n += 1
            else:
                fail_n += 1
                if len(errors) < 20:
                    errors.append(
                        {
                            "bitrix_id": row["bitrix_id"],
                            "inn": row["inn"],
                            "error": res.get("error"),
                        }
                    )

        return {
            "ok": True,
            "processed": len(rows),
            "ok_count": ok_n,
            "cached_hits": cached_n,
            "failed": fail_n,
            "errors": errors,
            "dadata_counts": self.store.counts(),
            "configured": dadata_configured(),
        }

    def push_to_bitrix(
        self,
        bitrix: Any,
        *,
        limit: int = 100,
        only_not_pushed: bool = True,
        sleep_sec: float = 0.12,
    ) -> dict[str, Any]:
        """Write DaData-enriched fields into Bitrix requisites + company cards."""
        import time

        limit = max(1, min(500, int(limit)))
        with self.clients.connect() as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()}
            if "bitrix_pushed_at" not in cols:
                conn.execute("ALTER TABLE companies ADD COLUMN bitrix_pushed_at TEXT")
            if only_not_pushed:
                rows = conn.execute(
                    """
                    SELECT bitrix_id, inn, title, director_name
                    FROM companies
                    WHERE inn IS NOT NULL AND inn != ''
                      AND director_name IS NOT NULL AND director_name != ''
                      AND (bitrix_pushed_at IS NULL OR bitrix_pushed_at = '')
                    ORDER BY bitrix_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT bitrix_id, inn, title, director_name
                    FROM companies
                    WHERE inn IS NOT NULL AND inn != ''
                      AND director_name IS NOT NULL AND director_name != ''
                    ORDER BY bitrix_id ASC
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()

        ok_n = 0
        fail_n = 0
        skipped_n = 0
        errors: list[dict[str, Any]] = []

        for row in rows:
            inn = str(row["inn"] or "")
            cid = str(row["bitrix_id"])
            cached = self.store.get(inn)
            if not cached or not cached.get("raw"):
                fail_n += 1
                if len(errors) < 30:
                    errors.append({"bitrix_id": cid, "inn": inn, "error": "no_dadata_cache"})
                continue
            suggestion = cached["raw"]
            if not isinstance(suggestion, dict):
                fail_n += 1
                continue
            rq_fields, company_fields = build_bitrix_fields_from_suggestion(suggestion)
            if not rq_fields and not company_fields:
                skipped_n += 1
                continue
            try:
                rid = _requisite_id_for_company(self.clients, cid)
                if not rid:
                    remote = bitrix.list_requisites_for_company(cid)
                    if remote:
                        rid = str(remote[0].get("ID") or "")
                if not rid:
                    fail_n += 1
                    if len(errors) < 30:
                        errors.append(
                            {"bitrix_id": cid, "inn": inn, "error": "no_requisite"}
                        )
                    continue
                if rq_fields:
                    bitrix.update_requisite(rid, rq_fields)
                if company_fields:
                    bitrix.update_company(cid, company_fields)
                now = _utc_now()
                with self.clients.connect() as conn:
                    conn.execute(
                        "UPDATE companies SET bitrix_pushed_at = ?, updated_at = ? WHERE bitrix_id = ?",
                        (now, now, cid),
                    )
                ok_n += 1
            except Exception as exc:  # noqa: BLE001
                fail_n += 1
                logger.warning("bitrix push failed company=%s inn=%s: %s", cid, inn, exc)
                if len(errors) < 30:
                    errors.append(
                        {"bitrix_id": cid, "inn": inn, "error": str(exc)[:300]}
                    )
            if sleep_sec > 0:
                time.sleep(sleep_sec)

        with self.clients.connect() as conn:
            pushed = conn.execute(
                "SELECT COUNT(*) AS n FROM companies "
                "WHERE bitrix_pushed_at IS NOT NULL AND bitrix_pushed_at != ''"
            ).fetchone()["n"]
            pending = conn.execute(
                """
                SELECT COUNT(*) AS n FROM companies
                WHERE inn IS NOT NULL AND inn != ''
                  AND director_name IS NOT NULL AND director_name != ''
                  AND (bitrix_pushed_at IS NULL OR bitrix_pushed_at = '')
                """
            ).fetchone()["n"]

        return {
            "ok": True,
            "processed": len(rows),
            "ok_count": ok_n,
            "failed": fail_n,
            "skipped": skipped_n,
            "errors": errors,
            "pushed_total": int(pushed),
            "pending": int(pending),
        }


class DaDataModule:
    name = "dadata"
    version = "1.1.0"

    def __init__(self) -> None:
        self.store = DaDataStore()
        self.enricher = DaDataEnricher(store=self.store)
        self._bitrix_factory: Any = None

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        if "clients" in ctx.extras:
            self.enricher.clients = ctx.extras["clients"]
        self._bitrix_factory = ctx.bitrix_factory
        ctx.extras["dadata"] = self.enricher
        logger.info(
            "dadata module ready configured=%s cache=%s",
            dadata_configured(),
            self.store.counts(),
        )

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {
            "ok": True,
            "configured": dadata_configured(),
            **self.store.counts(),
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Query

        @router.get("/status")
        def status() -> dict[str, Any]:
            pending = None
            pushed = None
            try:
                with self.enricher.clients.connect() as conn:
                    cols = {
                        r[1] for r in conn.execute("PRAGMA table_info(companies)").fetchall()
                    }
                    if "bitrix_pushed_at" in cols:
                        pushed = conn.execute(
                            "SELECT COUNT(*) AS n FROM companies "
                            "WHERE bitrix_pushed_at IS NOT NULL AND bitrix_pushed_at != ''"
                        ).fetchone()["n"]
                        pending = conn.execute(
                            """
                            SELECT COUNT(*) AS n FROM companies
                            WHERE inn IS NOT NULL AND inn != ''
                              AND director_name IS NOT NULL AND director_name != ''
                              AND (bitrix_pushed_at IS NULL OR bitrix_pushed_at = '')
                            """
                        ).fetchone()["n"]
            except Exception:  # noqa: BLE001
                pass
            return {
                "ok": True,
                "configured": dadata_configured(),
                "counts": self.store.counts(),
                "bitrix_pushed": pushed,
                "bitrix_pending": pending,
                "recent": self.store.recent(10),
                "env_hint": "DADATA_API_KEY required; DADATA_SECRET_KEY optional",
            }

        @router.get("/lookup")
        def lookup_get(
            inn: str = Query(...),
            force: bool = False,
            company_bitrix_id: str | None = None,
        ) -> dict[str, Any]:
            res = self.enricher.lookup_inn(
                inn, force=force, attach_company_id=company_bitrix_id
            )
            if not res.get("ok") and res.get("error") == "invalid_inn":
                raise HTTPException(400, "INN must be 10 or 12 digits")
            return res

        @router.post("/lookup")
        def lookup_post(
            inn: str = Query(...),
            force: bool = False,
            company_bitrix_id: str | None = None,
        ) -> dict[str, Any]:
            res = self.enricher.lookup_inn(
                inn, force=force, attach_company_id=company_bitrix_id
            )
            if not res.get("ok") and res.get("error") == "invalid_inn":
                raise HTTPException(400, "INN must be 10 or 12 digits")
            return res

        @router.post("/enrich")
        def enrich(
            limit: int = Query(50, ge=1, le=500),
            force: bool = False,
            only_missing_director: bool = True,
        ) -> dict[str, Any]:
            return self.enricher.enrich_companies(
                limit=limit,
                force=force,
                only_missing_director=only_missing_director,
            )

        @router.post("/push-bitrix")
        def push_bitrix(
            limit: int = Query(100, ge=1, le=500),
            only_not_pushed: bool = True,
        ) -> dict[str, Any]:
            if self._bitrix_factory is None:
                raise HTTPException(500, "bitrix factory not ready")
            client = self._bitrix_factory()
            if client is None:
                raise HTTPException(400, "BITRIX_WEBHOOK_URL not configured")
            try:
                return self.enricher.push_to_bitrix(
                    client,
                    limit=limit,
                    only_not_pushed=only_not_pushed,
                )
            finally:
                client.close()

        @router.get("/cache")
        def cache(limit: int = Query(30, ge=1, le=200)) -> dict[str, Any]:
            return {"ok": True, "items": self.store.recent(limit), "counts": self.store.counts()}
