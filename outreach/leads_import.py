"""CSV lead import with Bitrix clients + outbox dedup."""

from __future__ import annotations

import csv
import io
import logging
import re
from typing import Any

logger = logging.getLogger("ava-outreach.leads_import")

# Accept RU/EN header aliases
_HEADER_MAP = {
    "company": "company",
    "компания": "company",
    "company_name": "company",
    "segment": "segment",
    "сегмент": "segment",
    "pack": "segment",
    "pack_id": "segment",
    "website": "website",
    "сайт": "website",
    "site": "website",
    "url": "website",
    "email": "email",
    "e-mail": "email",
    "почта": "email",
    "phone": "phone",
    "телефон": "phone",
    "tel": "phone",
    "contact_name": "contact_name",
    "лпр": "contact_name",
    "lpr": "contact_name",
    "name": "contact_name",
    "контакт": "contact_name",
    "fio": "contact_name",
    "source": "source",
    "источник": "source",
}

_SEGMENT_TO_PACK = {
    "агенты": "agents_fintech",
    "агенты финтех": "agents_fintech",
    "финтех": "agents_fintech",
    "agents": "agents_fintech",
    "agents_fintech": "agents_fintech",
    "1с": "agents_1c",
    "1c": "agents_1c",
    "интеграторы 1с": "agents_1c",
    "интеграторы": "agents_1c",
    "agents_1c": "agents_1c",
    "бухгалтерский аутсорс": "agents_accounting",
    "бухгалтерия": "agents_accounting",
    "accounting": "agents_accounting",
    "agents_accounting": "agents_accounting",
    "стройка": "construction",
    "строительство": "construction",
    "construction": "construction",
    "блогеры": "blogger_agencies",
    "блогерские агентства": "blogger_agencies",
    "blogger": "blogger_agencies",
    "blogger_agencies": "blogger_agencies",
    "сельхоз": "agri",
    "агро": "agri",
    "agri": "agri",
    "аренда": "rental",
    "rental": "rental",
    "ломбарды": "lombards",
    "lombards": "lombards",
    "мфо": "mfo",
    "mfo": "mfo",
    "trade_in": "trade_in",
    "trade-in": "trade_in",
    "гиг": "gig",
    "gig": "gig",
    "scrap": "scrap",
    "вторсырьё": "scrap",
}


def _norm_header(h: str) -> str:
    key = (h or "").strip().lower().lstrip("\ufeff")
    return _HEADER_MAP.get(key, key)


def parse_leads_csv(csv_text: str) -> list[dict[str, str]]:
    text = (csv_text or "").strip()
    if not text:
        return []
    # Sniff delimiter
    sample = text[:2048]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        return []
    field_map = {_norm_header(f): f for f in reader.fieldnames if f}
    rows: list[dict[str, str]] = []
    for raw in reader:
        item: dict[str, str] = {}
        for canon, original in field_map.items():
            val = raw.get(original)
            item[canon] = (val or "").strip()
        email = item.get("email", "").strip().lower()
        if email and "@" in email:
            item["email"] = email
            rows.append(item)
    return rows


def resolve_pack_id(segment: str | None, explicit: str | None = None) -> str | None:
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower().replace("-", "_")
    if not segment:
        return None
    key = re.sub(r"\s+", " ", segment.strip().lower())
    return _SEGMENT_TO_PACK.get(key) or key.replace(" ", "_").replace("-", "_")


def check_lead_dup(
    *,
    email: str,
    company: str = "",
    outbox: Any,
    clients: Any | None = None,
) -> dict[str, Any]:
    """Return dedup hits against Bitrix clients mirror and outreach history."""
    email_n = (email or "").strip().lower()
    hits: list[dict[str, Any]] = []
    if clients is not None and email_n:
        try:
            found = clients.lookup_by_email(email_n)
            if found:
                hits.append({"source": "bitrix_clients", **found})
        except Exception as exc:  # noqa: BLE001
            logger.debug("clients lookup failed: %s", exc)
    if outbox is not None and email_n:
        row = outbox.find_by_email(email_n)
        if row:
            hits.append(
                {
                    "source": "outbox",
                    "outbox_id": row.id,
                    "status": row.status,
                    "contact_name": row.contact_name,
                    "company_id": row.company_id,
                    "email": row.email,
                }
            )
        sent = outbox.find_outreach_by_email(email_n)
        if sent and (not row or sent.id != row.id):
            hits.append(
                {
                    "source": "outreach_history",
                    "outbox_id": sent.id,
                    "status": sent.status,
                    "email": sent.email,
                }
            )
    if company and clients is not None:
        try:
            by_title = clients.lookup_by_company(company)
            for item in by_title[:5]:
                hits.append({"source": "bitrix_company", **item})
        except Exception as exc:  # noqa: BLE001
            logger.debug("company lookup failed: %s", exc)
    return {
        "ok": True,
        "email": email_n,
        "company": company,
        "duplicate": bool(hits),
        "hits": hits,
    }


def import_leads(
    *,
    csv_text: str,
    outbox: Any,
    clients: Any | None = None,
    pack_id: str | None = None,
    queue: bool = True,
    skip_duplicates: bool = True,
) -> dict[str, Any]:
    rows = parse_leads_csv(csv_text)
    if not rows:
        return {"ok": False, "error": "no_valid_rows", "imported": 0, "skipped": 0}

    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pack_ids: set[str] = set()

    for row in rows:
        email = row["email"]
        company = row.get("company") or ""
        contact = row.get("contact_name") or company or email.split("@")[0]
        seg = row.get("segment") or ""
        resolved_pack = resolve_pack_id(seg, pack_id)
        if resolved_pack:
            pack_ids.add(resolved_pack)

        dup = check_lead_dup(email=email, company=company, outbox=outbox, clients=clients)
        if dup["duplicate"] and skip_duplicates:
            skipped.append(
                {
                    "email": email,
                    "company": company,
                    "reason": "duplicate",
                    "hits": dup["hits"][:3],
                }
            )
            continue

        if queue:
            # company_id empty for CSV imports; title stored in contact_name
            display = contact
            if company and company.lower() not in display.lower():
                display = f"{contact} / {company}" if contact != company else company
            inserted = outbox.upsert_company(
                email=email,
                company_id=f"csv:{resolved_pack or 'import'}:{email}",
                company_title=display[:200],
            )
            # upsert_company returns True if inserted; if already pending, still ok
            existing = outbox.find_by_email(email)
            imported.append(
                {
                    "email": email,
                    "company": company,
                    "contact_name": contact,
                    "segment": seg,
                    "pack_id": resolved_pack,
                    "website": row.get("website") or "",
                    "phone": row.get("phone") or "",
                    "source": row.get("source") or "csv",
                    "outbox_id": existing.id if existing else None,
                    "inserted": bool(inserted),
                    "status": existing.status if existing else None,
                }
            )
        else:
            imported.append(
                {
                    "email": email,
                    "company": company,
                    "contact_name": contact,
                    "segment": seg,
                    "pack_id": resolved_pack,
                    "queued": False,
                }
            )

    return {
        "ok": True,
        "imported": len(imported),
        "skipped": len(skipped),
        "items": imported,
        "skipped_items": skipped,
        "pack_ids": sorted(pack_ids),
        "suggested_pack_id": pack_id or (sorted(pack_ids)[0] if len(pack_ids) == 1 else None),
    }
