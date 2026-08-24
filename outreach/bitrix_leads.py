"""Bitrix deal adapter for local Lead records."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("ava-outreach.bitrix_leads")


def sync_lead_to_bitrix(lead: dict[str, Any], *, dry_run: bool = False) -> dict[str, Any]:
    """Push local Lead to Bitrix deal (create if no bitrix_deal_id)."""
    if dry_run or (os.getenv("BITRIX_LEAD_SYNC") or "").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }:
        # default: allow when BITRIX_CREATE_DEAL or BITRIX_LEAD_SYNC=true
        pass

    enabled = (os.getenv("BITRIX_LEAD_SYNC") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } or (os.getenv("BITRIX_CREATE_DEAL") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "would_sync": True,
            "lead_id": lead.get("id"),
            "existing_deal_id": lead.get("bitrix_deal_id"),
        }
    if not enabled:
        return {
            "ok": False,
            "error": "bitrix_lead_sync_disabled",
            "hint": "Set BITRIX_LEAD_SYNC=true (or BITRIX_CREATE_DEAL=true)",
        }

    webhook = (os.getenv("BITRIX_WEBHOOK_URL") or "").strip()
    if not webhook:
        return {"ok": False, "error": "BITRIX_WEBHOOK_URL missing"}

    existing = (lead.get("bitrix_deal_id") or "").strip()
    if existing:
        return {"ok": True, "skipped": True, "bitrix_deal_id": existing, "reason": "already_linked"}

    from bitrix_client import BitrixClient
    from modules.accounts import AccountStore

    store = AccountStore()
    account = store.get_account(lead["account_id"]) if lead.get("account_id") else None
    person = store.get_person(lead["person_id"]) if lead.get("person_id") else None
    company_id = (account or {}).get("bitrix_company_id")
    title_bits = [
        (account or {}).get("legal_name") or (account or {}).get("brand_name") or "",
        (person or {}).get("full_name") or "",
        lead.get("source") or "outreach",
    ]
    title = " · ".join(b for b in title_bits if b) or f"Lead {lead.get('id')}"

    assigned = int(os.getenv("BITRIX_ASSIGNED_BY_ID") or "1")
    client = BitrixClient(webhook)
    deal_id = client.create_deal(
        title=title[:200],
        assigned_by_id=assigned,
        company_id=company_id,
        stage_id="NEW",
        comments=f"Synced from local Lead {lead.get('id')} status={lead.get('status')}",
        source_id="EMAIL",
    )
    # persist back
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with store.connect() as conn:
        conn.execute(
            "UPDATE leads SET bitrix_deal_id = ?, updated_at = ? WHERE id = ?",
            (str(deal_id), now, lead["id"]),
        )
    return {"ok": True, "bitrix_deal_id": str(deal_id), "lead_id": lead.get("id")}


def sync_lead_id_to_bitrix(lead_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    from modules.accounts import AccountStore

    store = AccountStore()
    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM leads WHERE id = ? AND tenant_id = ?",
            (lead_id, store.tenant_id),
        ).fetchone()
    if not row:
        return {"ok": False, "error": "lead_not_found"}
    return sync_lead_to_bitrix(dict(row), dry_run=dry_run)
