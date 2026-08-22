"""Layer F: company drill-down — aggregate CRM, outbox, sequences, consent."""

from __future__ import annotations

import json
from typing import Any

from core.paths import OUTBOX_DB
from modules.clients import ClientsStore, company_geo_row
from modules.consent import ConsentLedgerStore
from modules.sequences import SequenceStore
from outbox import OutboxStore


def _company_row(clients: ClientsStore, company_id: str) -> dict[str, Any] | None:
    cid = (company_id or "").strip()
    if not cid:
        return None
    with clients.connect() as conn:
        row = conn.execute(
            "SELECT * FROM companies WHERE bitrix_id = ? LIMIT 1",
            (cid,),
        ).fetchone()
    if not row:
        return None
    data = dict(row)
    for key in ("emails_json", "phones_json", "requisites_json"):
        raw = data.get(key) or "[]"
        try:
            data[key.replace("_json", "")] = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            data[key.replace("_json", "")] = []
    geo = company_geo_row(clients, cid)
    data.update(geo)
    return data


def _company_contacts(clients: ClientsStore, company_id: str) -> list[dict[str, Any]]:
    with clients.connect() as conn:
        rows = conn.execute(
            """
            SELECT bitrix_id, display_name, primary_email, post, synced_at
            FROM contacts
            WHERE company_bitrix_id = ?
            ORDER BY display_name ASC
            LIMIT 40
            """,
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _company_emails(clients: ClientsStore, company_id: str) -> list[dict[str, Any]]:
    with clients.connect() as conn:
        rows = conn.execute(
            """
            SELECT email, source, display_name, synced_at
            FROM client_emails
            WHERE company_bitrix_id = ? AND active = 1
            ORDER BY email ASC
            LIMIT 40
            """,
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _outbox_for_company(outbox: OutboxStore, company_id: str) -> list[dict[str, Any]]:
    items, _ = outbox.list_outbox(q=company_id, limit=30, offset=0)
    return [
        {
            "id": r.id,
            "email": r.email,
            "contact_name": r.contact_name,
            "status": r.status,
            "attempts": r.attempts,
            "sent_at": r.sent_at,
            "deal_id": r.deal_id,
            "last_error": r.last_error,
            "updated_at": r.updated_at,
        }
        for r in items
        if (r.company_id or "").strip() == company_id
    ]


def _sequences_for_company(seq: SequenceStore, company_id: str) -> list[dict[str, Any]]:
    with seq.connect() as conn:
        rows = conn.execute(
            """
            SELECT email, company_id, contact_name, current_step, status,
                   next_action_at, updated_at, created_at
            FROM sequence_leads
            WHERE company_id = ?
            ORDER BY updated_at DESC
            LIMIT 20
            """,
            (company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _consent_for_company(consent: ConsentLedgerStore, company_id: str) -> list[dict[str, Any]]:
    items, _ = consent.list_entries(q=company_id, limit=30, offset=0)
    return [i for i in items if (i.get("company_id") or "").strip() == company_id]


def build_company_card(
    company_id: str,
    *,
    clients: ClientsStore | None = None,
    outbox: OutboxStore | None = None,
    sequences: SequenceStore | None = None,
    consent: ConsentLedgerStore | None = None,
) -> dict[str, Any]:
    cid = (company_id or "").strip()
    if not cid:
        return {"ok": False, "error": "company_id_required"}

    clients = clients or ClientsStore()

    company = _company_row(clients, cid)
    if not company:
        return {"ok": False, "error": "company_not_found", "company_id": cid}

    outbox = outbox or OutboxStore(OUTBOX_DB)
    sequences = sequences or SequenceStore()
    consent = consent or ConsentLedgerStore()

    outbox_rows = _outbox_for_company(outbox, cid)
    seq_rows = _sequences_for_company(sequences, cid)
    consent_rows = _consent_for_company(consent, cid)

    return {
        "ok": True,
        "company_id": cid,
        "company": {
            "bitrix_id": cid,
            "title": company.get("title") or "",
            "inn": company.get("inn") or "",
            "ogrn": company.get("ogrn") or "",
            "city": company.get("city") or "",
            "region": company.get("region") or "",
            "timezone": company.get("timezone") or company.get("timezone_raw") or "",
            "director_name": company.get("director_name") or "",
            "director_greeting": company.get("director_greeting") or "",
            "primary_email": company.get("primary_email") or "",
            "emails": company.get("emails") or [],
            "phones": company.get("phones") or [],
            "synced_at": company.get("synced_at") or "",
        },
        "contacts": _company_contacts(clients, cid),
        "emails": _company_emails(clients, cid),
        "outbox": outbox_rows,
        "sequences": seq_rows,
        "consent": consent_rows,
        "summary": {
            "outbox_total": len(outbox_rows),
            "outbox_sent": sum(1 for r in outbox_rows if r.get("status") in ("sent", "replied")),
            "sequences_active": sum(1 for r in seq_rows if r.get("status") == "active"),
            "consent_entries": len(consent_rows),
        },
    }
