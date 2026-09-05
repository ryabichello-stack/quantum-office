from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.adapters.party_lookup import PartyLookupAdapter, extract_party_fields, normalize_inn
from app.models.party_cache import PartyCache
from app.services.events import emit_event


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _party_cache_to_dict(row: PartyCache) -> dict[str, Any]:
    return {
        "inn": row.inn,
        "ogrn": row.ogrn,
        "company_name": row.company_name,
        "director_name": row.director_name,
        "address": row.address,
        "okved": row.okved,
        "status": row.status,
        "party_type": row.party_type,
        "fetched_at": row.fetched_at.isoformat() if row.fetched_at else None,
        "raw": row.raw_json,
    }


def _pick_best_suggestion(suggestions: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not suggestions:
        return None
    for suggestion in suggestions:
        data = suggestion.get("data") if isinstance(suggestion.get("data"), dict) else {}
        if str(data.get("branch_type") or "").upper() == "MAIN":
            return suggestion
    return suggestions[0]


def upsert_party_cache(db: Session, suggestion: dict[str, Any]) -> PartyCache:
    flat = extract_party_fields(suggestion)
    inn = normalize_inn(flat.get("inn"))
    if not inn:
        raise ValueError("DaData suggestion has no INN")

    row = db.get(PartyCache, inn)
    if row is None:
        row = PartyCache(inn=inn)
        db.add(row)

    row.ogrn = flat.get("ogrn")
    row.company_name = flat.get("company_name")
    row.director_name = flat.get("director_name")
    row.address = flat.get("address")
    row.okved = flat.get("okved")
    row.status = flat.get("status")
    row.party_type = flat.get("party_type")
    row.raw_json = suggestion
    row.fetched_at = _utc_now()
    db.flush()
    return row


def lookup_party_by_inn(
    db: Session,
    inn: str,
    *,
    tenant_id: UUID | None = None,
    force: bool = False,
    adapter: PartyLookupAdapter | None = None,
) -> dict[str, Any]:
    """
    Resolve party by INN: PG cache first, then DaData findById.
    Emits party.lookup or party.lookup_failed for tenant-scoped calls.
    """
    inn_n = normalize_inn(inn)
    if not inn_n:
        result = {"ok": False, "error": "invalid_inn", "inn": inn}
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.lookup_failed",
                source="tenant.party.lookup",
                payload={"inn": inn, "reason": "invalid_inn"},
            )
        return result

    if not force:
        cached = db.get(PartyCache, inn_n)
        if cached:
            party = _party_cache_to_dict(cached)
            if tenant_id:
                emit_event(
                    db,
                    tenant_id=tenant_id,
                    event_type="party.lookup",
                    source="tenant.party.lookup",
                    payload={"inn": inn_n, "cached": True, "company_name": party.get("company_name")},
                )
            return {
                "ok": True,
                "cached": True,
                "inn": inn_n,
                "party": party,
                "flat": extract_party_fields(cached.raw_json if isinstance(cached.raw_json, dict) else {}),
            }

    api = adapter or PartyLookupAdapter()
    if not api.configured():
        result = {
            "ok": False,
            "error": "dadata_not_configured",
            "inn": inn_n,
            "hint": "Set DADATA_API_KEY in environment",
        }
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.lookup_failed",
                source="tenant.party.lookup",
                payload={"inn": inn_n, "reason": "dadata_not_configured"},
            )
        return result

    try:
        suggestions = api.find_by_inn(inn_n)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": "upstream_error", "inn": inn_n, "detail": str(exc)[:400]}
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.lookup_failed",
                source="tenant.party.lookup",
                payload={"inn": inn_n, "reason": "upstream_error"},
            )
        return result

    best = _pick_best_suggestion(suggestions)
    if not best:
        result = {"ok": False, "error": "not_found", "inn": inn_n}
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.lookup_failed",
                source="tenant.party.lookup",
                payload={"inn": inn_n, "reason": "not_found"},
            )
        return result

    row = upsert_party_cache(db, best)
    party = _party_cache_to_dict(row)
    flat = extract_party_fields(best)
    if tenant_id:
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="party.lookup",
            source="tenant.party.lookup",
            payload={"inn": inn_n, "cached": False, "company_name": flat.get("company_name")},
        )
    return {
        "ok": True,
        "cached": False,
        "inn": inn_n,
        "party": party,
        "flat": flat,
        "suggestions_count": len(suggestions),
    }


def enrich_lead_from_inn(
    db: Session,
    lead: Any,
    inn: str | None,
    *,
    tenant_id: UUID,
    source: str = "leads.enrich",
    adapter: PartyLookupAdapter | None = None,
) -> dict[str, Any]:
    """Attach DaData party snapshot to a lead when INN is provided."""
    from app.models.lead import Lead

    if not isinstance(lead, Lead):
        return {"enriched": False, "reason": "invalid_lead"}

    inn_n = normalize_inn(inn)
    if not inn_n:
        return {"enriched": False, "reason": "invalid_inn"}

    lead.inn = inn_n
    lookup = lookup_party_by_inn(db, inn_n, tenant_id=tenant_id, adapter=adapter)
    if not lookup.get("ok"):
        return {"enriched": False, "reason": lookup.get("error"), "lookup": lookup}

    flat = lookup.get("flat") or {}
    lead.party_json = {"flat": flat, "party": lookup.get("party")}
    lead.party_enriched_at = _utc_now()
    if not lead.company and flat.get("company_name"):
        lead.company = str(flat["company_name"])[:160]

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="party.enriched",
        source=source,
        payload={
            "lead_id": str(lead.id),
            "inn": inn_n,
            "company_name": flat.get("company_name"),
            "cached": lookup.get("cached"),
        },
    )
    db.flush()
    return {"enriched": True, "lookup": lookup}


def _flatten_suggestion_for_client(suggestion: dict[str, Any]) -> dict[str, Any]:
    flat = extract_party_fields(suggestion)
    return {
        "value": flat.get("value") or flat.get("company_name"),
        "inn": flat.get("inn"),
        "company_name": flat.get("company_name"),
        "address": flat.get("address"),
        "status": flat.get("status"),
        "party_type": flat.get("party_type"),
    }


def suggest_parties_by_query(
    db: Session,
    query: str,
    *,
    tenant_id: UUID | None = None,
    count: int = 5,
    source: str = "public.party.suggest",
    adapter: PartyLookupAdapter | None = None,
) -> dict[str, Any]:
    """Autocomplete legal entities by name or INN prefix (DaData suggest)."""
    q = (query or "").strip()
    if len(q) < 2:
        result = {"ok": False, "error": "query_too_short", "query": q}
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.suggest_failed",
                source=source,
                payload={"query": q, "reason": "query_too_short"},
            )
        return result

    api = adapter or PartyLookupAdapter()
    if not api.configured():
        result = {
            "ok": False,
            "error": "dadata_not_configured",
            "query": q,
            "hint": "Set DADATA_API_KEY in environment",
        }
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.suggest_failed",
                source=source,
                payload={"query": q, "reason": "dadata_not_configured"},
            )
        return result

    try:
        raw = api.suggest_parties(q, count=count)
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": "upstream_error", "query": q, "detail": str(exc)[:400]}
        if tenant_id:
            emit_event(
                db,
                tenant_id=tenant_id,
                event_type="party.suggest_failed",
                source=source,
                payload={"query": q, "reason": "upstream_error"},
            )
        return result

    suggestions = [_flatten_suggestion_for_client(s) for s in raw if isinstance(s, dict)]
    suggestions = [s for s in suggestions if s.get("inn") or s.get("company_name")]

    if tenant_id:
        emit_event(
            db,
            tenant_id=tenant_id,
            event_type="party.suggest",
            source=source,
            payload={"query": q, "count": len(suggestions)},
        )

    return {"ok": True, "query": q, "suggestions": suggestions}


def build_tenant_legal_profile(flat: dict[str, Any]) -> dict[str, Any]:
    """Normalize DaData flat fields into tenants.settings.legal (E1.15)."""
    ogrn = flat.get("ogrn")
    profile: dict[str, Any] = {
        "inn": flat.get("inn"),
        "company_name": flat.get("company_name"),
        "address": flat.get("address"),
        "okved": flat.get("okved"),
        "enriched_at": _utc_now().isoformat(),
    }
    if ogrn:
        profile["ogrn"] = ogrn
        if flat.get("party_type") == "INDIVIDUAL":
            profile["ogrnip"] = ogrn
    return {key: value for key, value in profile.items() if value}


def enrich_tenant_legal_from_inn(
    db: Session,
    tenant: Any,
    inn: str,
    *,
    tenant_id: UUID,
    source: str = "tenant.legal.enrich",
    adapter: PartyLookupAdapter | None = None,
) -> dict[str, Any]:
    """Persist DaData party snapshot to tenant.settings.legal."""
    from app.models.tenant import Tenant
    from sqlalchemy.orm.attributes import flag_modified

    if not isinstance(tenant, Tenant):
        return {"enriched": False, "reason": "invalid_tenant"}

    inn_n = normalize_inn(inn)
    if not inn_n:
        return {"enriched": False, "reason": "invalid_inn"}

    lookup = lookup_party_by_inn(db, inn_n, tenant_id=tenant_id, adapter=adapter)
    if not lookup.get("ok"):
        return {"enriched": False, "reason": lookup.get("error"), "lookup": lookup}

    flat = lookup.get("flat") or {}
    legal = build_tenant_legal_profile(flat)
    settings = dict(tenant.settings or {})
    settings["legal"] = legal
    tenant.settings = settings
    flag_modified(tenant, "settings")

    emit_event(
        db,
        tenant_id=tenant_id,
        event_type="party.enriched",
        source=source,
        payload={
            "target": "tenant",
            "inn": inn_n,
            "company_name": legal.get("company_name"),
            "cached": lookup.get("cached"),
        },
    )
    db.flush()
    return {"enriched": True, "legal": legal, "lookup": lookup}
