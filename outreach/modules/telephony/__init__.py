"""Inbound telephony leads → Bitrix CRM (contact / company / deal / timeline)."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from bitrix_client import (
    BitrixClient,
    normalize_email,
    normalize_phone,
)
from core.paths import MODULES_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.telephony")

# Default industry for new companies created from calls (Ломбарды)
DEFAULT_CALL_INDUSTRY = "UC_TM21P2"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _split_name(full: str) -> tuple[str, str]:
    parts = [p for p in (full or "").strip().split() if p]
    if not parts:
        return "Клиент", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on", "да"}


class TelephonyLeadStore:
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
                CREATE TABLE IF NOT EXISTS telephony_leads (
                    call_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    contact_id TEXT,
                    company_id TEXT,
                    deal_id TEXT,
                    status TEXT NOT NULL DEFAULT 'ok'
                )
                """
            )

    def get(self, call_id: str) -> dict[str, Any] | None:
        cid = (call_id or "").strip()
        if not cid:
            return None
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM telephony_leads WHERE call_id = ?", (cid,)
            ).fetchone()
        return dict(row) if row else None

    def save(
        self,
        *,
        call_id: str,
        payload: dict[str, Any],
        result: dict[str, Any],
        status: str = "ok",
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telephony_leads(
                    call_id, created_at, payload_json, result_json,
                    contact_id, company_id, deal_id, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(call_id) DO UPDATE SET
                    result_json=excluded.result_json,
                    contact_id=excluded.contact_id,
                    company_id=excluded.company_id,
                    deal_id=excluded.deal_id,
                    status=excluded.status
                """,
                (
                    call_id,
                    _utc_now(),
                    json.dumps(payload, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False),
                    str(result.get("contact_id") or "") or None,
                    str(result.get("company_id") or "") or None,
                    str(result.get("deal_id") or "") or None,
                    status,
                ),
            )

    def counts(self) -> dict[str, int]:
        with self.connect() as conn:
            total = conn.execute("SELECT COUNT(*) AS n FROM telephony_leads").fetchone()["n"]
            ok = conn.execute(
                "SELECT COUNT(*) AS n FROM telephony_leads WHERE status = 'ok'"
            ).fetchone()["n"]
        return {"leads": int(total), "ok": int(ok)}


def _lead_name(lead: dict[str, Any]) -> str:
    return str(
        lead.get("name")
        or lead.get("contact_name")
        or lead.get("caller_name")
        or ""
    ).strip()


def _lead_company(lead: dict[str, Any]) -> str:
    return str(
        lead.get("company")
        or lead.get("company_name")
        or lead.get("meeting_company")
        or ""
    ).strip()


def _lead_meeting(lead: dict[str, Any]) -> bool:
    return _truthy(
        lead.get("meeting")
        if lead.get("meeting") is not None
        else lead.get("meeting_requested")
    )


def build_timeline_comment(lead: dict[str, Any]) -> str:
    meeting = _lead_meeting(lead)
    lines = [
        "📞 Входящий звонок AVA",
        "",
        f"Имя: {_lead_name(lead) or '—'}",
        f"Телефон: {lead.get('phone') or lead.get('caller_number') or '—'}",
        f"Email: {lead.get('email') or lead.get('attendee_email') or '—'}",
        f"Компания: {_lead_company(lead) or '—'}",
        f"Интерес: {lead.get('interest') or '—'}",
        f"Встреча: {'да' if meeting else 'нет'}",
    ]
    when = lead.get("meeting_time") or lead.get("meeting_start") or ""
    if when:
        lines.append(f"Дата/время встречи: {when}")
    telemost = lead.get("telemost_join_url") or ""
    if telemost:
        lines.append(f"Телемост: {telemost}")
    summary = (lead.get("summary") or "").strip()
    if summary:
        lines.extend(["", "Резюме:", summary])
    call_id = lead.get("call_id") or ""
    if call_id:
        lines.extend(["", f"Call ID: {call_id}"])
    return "\n".join(lines)


def is_qualified_lead(lead: dict[str, Any]) -> bool:
    """Create a deal when there is something actionable."""
    if _lead_meeting(lead):
        return True
    if (lead.get("telemost_join_url") or "").strip():
        return True
    if (lead.get("email") or lead.get("attendee_email") or "").strip():
        return True
    if _lead_company(lead):
        return True
    if (lead.get("interest") or "").strip():
        return True
    if _truthy(lead.get("interested")) or _truthy(lead.get("email_requested")):
        return True
    summary = (lead.get("summary") or "").strip()
    if summary and "AI-разбор не успел" not in summary:
        return True
    return False


def ingest_telephony_lead(
    bitrix: BitrixClient,
    store: TelephonyLeadStore,
    payload: dict[str, Any],
    *,
    settings: Any = None,
) -> dict[str, Any]:
    """Upsert contact/company, create CALL deal, write timeline. Idempotent by call_id."""
    call_id = str(payload.get("call_id") or "").strip()
    if call_id:
        existing = store.get(call_id)
        if existing and existing.get("status") == "ok" and existing.get("deal_id"):
            return {
                "ok": True,
                "duplicate": True,
                "call_id": call_id,
                "contact_id": existing.get("contact_id"),
                "company_id": existing.get("company_id"),
                "deal_id": existing.get("deal_id"),
            }

    def cfg(key: str, default: str = "") -> str:
        if settings is not None:
            val = settings.get(key)
            if val is not None and str(val) != "":
                return str(val)
        return os.getenv(key, default)

    def cfg_int(key: str, default: int) -> int:
        raw = cfg(key, str(default))
        try:
            return int(raw)
        except ValueError:
            return default

    assigned = cfg_int("BITRIX_ASSIGNED_BY_ID", 1)
    stage = cfg("BITRIX_CALL_DEAL_STAGE_ID") or cfg("BITRIX_DEAL_STAGE_ID", "NEW")
    industry = cfg("BITRIX_CALL_COMPANY_INDUSTRY", DEFAULT_CALL_INDUSTRY)

    name_raw = _lead_name(payload)
    phone = normalize_phone(payload.get("phone") or payload.get("caller_number"))
    email = normalize_email(payload.get("email") or payload.get("attendee_email"))
    company_title = _lead_company(payload)
    first, last = _split_name(name_raw)

    company_id: int | None = None
    company_created = False
    if company_title:
        found = bitrix.find_company_by_title(company_title)
        if found:
            company_id = int(found["ID"])
        else:
            company_id = bitrix.create_company(
                title=company_title,
                email=email,
                phone=phone,
                assigned_by_id=assigned,
                industry=industry or None,
            )
            company_created = True

    contact_id: int | None = None
    contact_created = False
    contacts: list[dict[str, Any]] = []
    if phone:
        contacts = bitrix.find_contacts_by_phone(phone)
    if not contacts and email:
        contacts = bitrix.find_contacts_by_email(email)
    if contacts:
        contact_id = int(contacts[0]["ID"])
        # Link company if missing
        if company_id and not contacts[0].get("COMPANY_ID"):
            try:
                bitrix.call(
                    "crm.contact.update",
                    {"id": contact_id, "fields": {"COMPANY_ID": company_id}},
                )
            except Exception:  # noqa: BLE001
                logger.debug("contact company link failed", exc_info=True)
    else:
        # Need at least phone or email or name to create contact
        if phone or email or name_raw:
            contact_id = bitrix.create_contact(
                name=first,
                last_name=last,
                phone=phone,
                email=email,
                company_id=company_id,
                assigned_by_id=assigned,
            )
            contact_created = True

    deal_id: int | None = None
    deal_created = False
    deal_reused = False
    qualified = is_qualified_lead(payload)

    if qualified and (contact_id or company_id):
        if contact_id:
            open_deals = bitrix.find_open_deals_for_contact(contact_id, source_id="CALL")
            if open_deals:
                deal_id = int(open_deals[0]["ID"])
                deal_reused = True
        if deal_id is None:
            who = name_raw or phone or email or company_title or "без имени"
            title = f"Входящий звонок AVA: {who}"
            deal_id = bitrix.create_deal(
                title=title,
                assigned_by_id=assigned,
                company_id=company_id,
                contact_id=contact_id,
                stage_id=stage,
                comments=(payload.get("summary") or "")[:2000],
                source_id="CALL",
            )
            deal_created = True

    comment = build_timeline_comment(payload)
    timeline_ok = False
    if deal_id:
        try:
            bitrix.add_timeline_comment(deal_id, comment, entity_type="deal")
            timeline_ok = True
        except Exception:  # noqa: BLE001
            logger.warning("timeline on deal failed", exc_info=True)
    elif contact_id:
        try:
            bitrix.add_timeline_comment(contact_id, comment, entity_type="contact")
            timeline_ok = True
        except Exception:  # noqa: BLE001
            logger.warning("timeline on contact failed", exc_info=True)

    result = {
        "ok": True,
        "call_id": call_id or None,
        "qualified": qualified,
        "contact_id": contact_id,
        "contact_created": contact_created,
        "company_id": company_id,
        "company_created": company_created,
        "deal_id": deal_id,
        "deal_created": deal_created,
        "deal_reused": deal_reused,
        "timeline_ok": timeline_ok,
    }
    if call_id:
        store.save(call_id=call_id, payload=payload, result=result, status="ok")

    # Contact policy: stop/cooldown email after call outcomes
    try:
        from modules.policy import ContactPolicyStore
        from modules.sequences import SequenceStore

        if company_id:
            meeting = _lead_meeting(payload)
            refused = _truthy(payload.get("refused")) or (
                str(payload.get("outcome") or "").lower()
                in ("refused", "not_interested", "negative")
            )
            interested = _truthy(payload.get("interested")) or qualified
            outcome = str(payload.get("outcome") or "")
            if meeting:
                outcome = outcome or "meeting"
            elif refused:
                outcome = outcome or "refused"
            elif interested:
                outcome = outcome or "interested"
            else:
                outcome = outcome or "call"
            ContactPolicyStore().note_call(
                str(company_id),
                result=outcome,
                meeting=meeting,
                refused=refused,
                interested=interested and not refused,
            )
            if meeting or refused or (_truthy(payload.get("do_not_email"))):
                SequenceStore().stop(
                    company_id=str(company_id),
                    reason="call_meeting"
                    if meeting
                    else ("call_refused" if refused else "call_policy"),
                )
                if email:
                    SequenceStore().stop(
                        email=str(email),
                        reason="call_meeting"
                        if meeting
                        else ("call_refused" if refused else "call_policy"),
                    )
    except Exception:  # noqa: BLE001
        logger.debug("policy/sequence after call failed", exc_info=True)

    logger.info(
        "telephony lead call_id=%s contact=%s company=%s deal=%s qualified=%s",
        call_id,
        contact_id,
        company_id,
        deal_id,
        qualified,
    )
    return result


class TelephonyModule:
    name = "telephony"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = TelephonyLeadStore()
        self._bitrix_factory: Any = None
        self._settings: Any = None

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        self._bitrix_factory = ctx.bitrix_factory
        self._settings = ctx.settings
        ctx.extras["telephony"] = self
        logger.info("telephony module ready %s", self.store.counts())

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, **self.store.counts()}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException, Request

        @router.get("/status")
        def status() -> dict[str, Any]:
            return {"ok": True, **self.store.counts()}

        @router.post("/lead")
        async def lead(request: Request) -> dict[str, Any]:
            if self._bitrix_factory is None:
                raise HTTPException(500, "bitrix factory not ready")
            try:
                body = await request.json()
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(400, f"invalid json: {exc}") from exc
            if not isinstance(body, dict):
                raise HTTPException(400, "json object required")
            client = self._bitrix_factory()
            if client is None:
                raise HTTPException(400, "BITRIX_WEBHOOK_URL missing")
            try:
                return ingest_telephony_lead(
                    client,
                    self.store,
                    body,
                    settings=self._settings,
                )
            finally:
                client.close()