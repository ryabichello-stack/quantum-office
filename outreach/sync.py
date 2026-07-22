"""Pull Bitrix companies into local SQLite outbox (unique email)."""

from __future__ import annotations

import logging
from typing import Any

from bitrix_client import BitrixClient, company_display_name, extract_emails_from_fields
from outbox import OutboxStore

logger = logging.getLogger("ava-outreach.sync")


def sync_companies(store: OutboxStore, client: BitrixClient) -> dict[str, Any]:
    scanned = 0
    with_email = 0
    inserted = 0
    skipped_no_email = 0
    already = 0

    for company in client.list_companies():
        scanned += 1
        emails = extract_emails_from_fields(company)
        if not emails:
            skipped_no_email += 1
            continue
        with_email += 1
        cid = str(company.get("ID") or "")
        title = company_display_name(company)
        email = emails[0]
        if store.upsert_company(email=email, company_id=cid, company_title=title):
            inserted += 1
        else:
            already += 1

    report = {
        "ok": True,
        "entity": "company",
        "scanned_companies": scanned,
        "companies_with_email": with_email,
        "skipped_no_email": skipped_no_email,
        "inserted_new": inserted,
        "already_known": already,
        "outbox": store.counts(),
    }
    logger.info("sync done: %s", report)
    return report


# Back-compat alias used by older CLI docs / callers
def sync_contacts(store: OutboxStore, client: BitrixClient) -> dict[str, Any]:
    return sync_companies(store, client)
