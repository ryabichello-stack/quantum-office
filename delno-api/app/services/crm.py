"""CRM-lite over tenant leads — tools-first, no Bitrix required."""

from __future__ import annotations

import uuid
from collections import Counter
from typing import Any

from sqlalchemy.orm import Session

from app.core.tenant import TenantContext
from app.models.lead import Lead
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.leads import create_lead_record

FUNNEL_STAGES = (
    "NEW",
    "ENRICHED",
    "CONTACTED",
    "IN_SEQUENCE",
    "REPLIED",
    "MEETING",
    "WON",
    "LOST",
    "PAUSED",
)

_STATUS_ALIASES = {
    "new": "NEW",
    "enriched": "ENRICHED",
    "contacted": "CONTACTED",
    "in_sequence": "IN_SEQUENCE",
    "in-sequence": "IN_SEQUENCE",
    "replied": "REPLIED",
    "meeting": "MEETING",
    "won": "WON",
    "lost": "LOST",
    "paused": "PAUSED",
    "qualified": "CONTACTED",
}


def normalize_lifecycle(status: str | None) -> str:
    raw = (status or "new").strip()
    if not raw:
        return "NEW"
    upper = raw.upper().replace("-", "_").replace(" ", "_")
    if upper in FUNNEL_STAGES:
        return upper
    return _STATUS_ALIASES.get(raw.lower(), upper if upper.isalpha() else "NEW")


def _lead_dict(lead: Lead) -> dict[str, Any]:
    return {
        "id": str(lead.id),
        "name": lead.name,
        "phone": lead.phone,
        "email": lead.email,
        "company": lead.company,
        "website": lead.website,
        "inn": lead.inn,
        "source": lead.source,
        "status": normalize_lifecycle(lead.status),
        "party_enriched": lead.party_json is not None,
        "conversation_id": str(lead.conversation_id) if lead.conversation_id else None,
        "created_at": lead.created_at.isoformat() if lead.created_at else None,
    }


def funnel_counts(db: Session, ctx: TenantContext) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    leads = db.query(Lead).filter(Lead.tenant_id == ctx.tenant_id).all()
    for lead in leads:
        stage = normalize_lifecycle(lead.status)
        if stage == "NEW" and lead.party_json:
            stage = "ENRICHED"
        counter[stage] += 1
    stages = {stage: int(counter.get(stage, 0)) for stage in FUNNEL_STAGES}
    return {
        "ok": True,
        "tenant_slug": ctx.tenant_slug,
        "total": sum(stages.values()),
        "stages": stages,
        "funnel": FUNNEL_STAGES,
    }


def list_leads(
    db: Session,
    ctx: TenantContext,
    *,
    limit: int = 50,
    status: str | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    query = db.query(Lead).filter(Lead.tenant_id == ctx.tenant_id)
    if status:
        want = normalize_lifecycle(status)
        # match both normalized and legacy lowercase
        query = query.filter(Lead.status.in_([want, want.lower(), status.strip()]))
    rows = query.order_by(Lead.created_at.desc()).limit(max(1, min(limit, 200))).all()
    items = [_lead_dict(row) for row in rows]
    if q:
        needle = q.strip().lower()
        items = [
            item
            for item in items
            if needle in " ".join(
                str(item.get(k) or "") for k in ("name", "company", "phone", "email", "inn")
            ).lower()
        ]
    return {"ok": True, "tenant_slug": ctx.tenant_slug, "count": len(items), "items": items}


def get_lead(db: Session, ctx: TenantContext, lead_id: str) -> dict[str, Any]:
    try:
        uid = uuid.UUID(str(lead_id))
    except ValueError:
        return {"ok": False, "error": "invalid_lead_id"}
    lead = db.query(Lead).filter(Lead.id == uid, Lead.tenant_id == ctx.tenant_id).one_or_none()
    if not lead:
        return {"ok": False, "error": "not_found"}
    return {"ok": True, "lead": _lead_dict(lead), "party": lead.party_json}


def set_lifecycle(
    db: Session,
    ctx: TenantContext,
    *,
    lead_id: str,
    status: str,
) -> dict[str, Any]:
    stage = normalize_lifecycle(status)
    if stage not in FUNNEL_STAGES:
        return {"ok": False, "error": "invalid_status", "allowed": list(FUNNEL_STAGES)}
    try:
        uid = uuid.UUID(str(lead_id))
    except ValueError:
        return {"ok": False, "error": "invalid_lead_id"}
    lead = db.query(Lead).filter(Lead.id == uid, Lead.tenant_id == ctx.tenant_id).one_or_none()
    if not lead:
        return {"ok": False, "error": "not_found"}
    old = lead.status
    lead.status = stage
    db.add(lead)
    write_audit(
        db,
        ctx,
        action="crm.lifecycle_set",
        resource=f"lead:{lead.id}",
        old_value={"status": old},
        new_value={"status": stage},
    )
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="crm.lifecycle_changed",
        category="operational",
        source="crm.lifecycle_set",
        payload={"lead_id": str(lead.id), "from": old, "to": stage},
    )
    return {"ok": True, "lead": _lead_dict(lead)}


def suggest_next(db: Session, ctx: TenantContext, *, lead_id: str | None = None) -> dict[str, Any]:
    lead_payload = None
    stage = "NEW"
    if lead_id:
        got = get_lead(db, ctx, lead_id)
        if not got.get("ok"):
            return got
        lead_payload = got["lead"]
        stage = str(lead_payload.get("status") or "NEW")
    suggestions = {
        "NEW": [
            "enrich_party" if not (lead_payload or {}).get("party_enriched") else "lifecycle_to_CONTACTED",
            "send_intro_mail",
            "schedule_call",
        ],
        "ENRICHED": ["send_intro_mail", "add_to_outreach_sequence", "lifecycle_to_IN_SEQUENCE"],
        "CONTACTED": ["follow_up_mail", "suggest_calendar_slots", "lifecycle_to_MEETING"],
        "IN_SEQUENCE": ["check_replies", "outreach.preview", "pause_if_bounce"],
        "REPLIED": ["create_conference", "suggest_calendar_slots", "lifecycle_to_MEETING"],
        "MEETING": ["send_agenda", "lifecycle_to_WON_or_LOST"],
        "WON": ["upload_knowledge_snippet", "request_referral"],
        "LOST": ["lifecycle_to_PAUSED", "revisit_in_90d"],
        "PAUSED": ["reactivate_to_NEW"],
    }
    return {
        "ok": True,
        "stub": False,
        "tenant_slug": ctx.tenant_slug,
        "lead": lead_payload,
        "status": stage,
        "next_actions": suggestions.get(stage, ["review_manually"]),
        "note": "Deterministic CRM-lite suggestions (no LLM).",
    }


def list_companies(db: Session, ctx: TenantContext, *, limit: int = 50, q: str | None = None) -> dict[str, Any]:
    leads = db.query(Lead).filter(Lead.tenant_id == ctx.tenant_id).order_by(Lead.created_at.desc()).all()
    by_key: dict[str, dict[str, Any]] = {}
    for lead in leads:
        company = (lead.company or lead.name or "").strip()
        if not company:
            continue
        key = company.lower()
        if key not in by_key:
            by_key[key] = {
                "company": company,
                "inn": lead.inn,
                "website": lead.website,
                "phones": [],
                "emails": [],
                "leads": [],
                "status": normalize_lifecycle(lead.status),
            }
        entry = by_key[key]
        if lead.phone and lead.phone not in entry["phones"]:
            entry["phones"].append(lead.phone)
        if lead.email and lead.email not in entry["emails"]:
            entry["emails"].append(lead.email)
        if lead.inn and not entry.get("inn"):
            entry["inn"] = lead.inn
        entry["leads"].append(str(lead.id))
        # keep most advanced stage roughly by funnel index
        cur = entry["status"]
        if FUNNEL_STAGES.index(normalize_lifecycle(lead.status)) > FUNNEL_STAGES.index(cur):
            entry["status"] = normalize_lifecycle(lead.status)
    items = list(by_key.values())
    if q:
        needle = q.strip().lower()
        items = [i for i in items if needle in i["company"].lower() or needle in str(i.get("inn") or "")]
    items = items[: max(1, min(limit, 200))]
    return {"ok": True, "tenant_slug": ctx.tenant_slug, "count": len(items), "items": items}


def upsert_company(
    db: Session,
    ctx: TenantContext,
    *,
    company: str,
    phone: str | None = None,
    email: str | None = None,
    website: str | None = None,
    inn: str | None = None,
    contact_name: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    company = (company or "").strip()
    if not company:
        return {"ok": False, "error": "company_required"}
    # dedupe by company (+ optional inn)
    query = db.query(Lead).filter(Lead.tenant_id == ctx.tenant_id, Lead.company.ilike(company))
    if inn:
        query = query.filter(Lead.inn == inn.strip())
    existing = query.order_by(Lead.created_at.desc()).first()
    if existing:
        if phone:
            existing.phone = phone.strip()[:60]
        if email:
            existing.email = email.strip()[:160]
        if website:
            existing.website = website.strip()[:255]
        if inn:
            existing.inn = inn.strip()[:12]
        if contact_name:
            existing.name = contact_name.strip()[:120]
        if status:
            existing.status = normalize_lifecycle(status)
        db.add(existing)
        write_audit(
            db,
            ctx,
            action="crm.company_upsert",
            resource=f"lead:{existing.id}",
            new_value={"company": company, "updated": True},
        )
        return {"ok": True, "created": False, "lead": _lead_dict(existing)}

    phone_val = (phone or "").strip() or "n/a"
    name_val = (contact_name or company).strip()[:120]
    lead, meta = create_lead_record(
        db,
        ctx,
        name=name_val,
        phone=phone_val[:60],
        email=email.strip()[:160] if email else None,
        company=company[:160],
        website=website.strip()[:255] if website else None,
        inn=inn.strip() if inn else None,
        source="crm.upsert",
        audit_action="crm.company_upsert",
        event_source="crm.company_upsert",
        channel="crm",
    )
    if status:
        lead.status = normalize_lifecycle(status)
        db.add(lead)
    return {
        "ok": True,
        "created": True,
        "lead": _lead_dict(lead),
        "party_enriched": meta["enrichment"].get("enriched"),
    }
