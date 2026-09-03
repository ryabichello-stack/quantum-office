from pydantic import BaseModel, Field

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.party_enrichment import enrich_tenant_legal_from_inn, lookup_party_by_inn, suggest_parties_by_query
from app.services.tenant_settings_ingest import sync_tenant_settings_for_ctx
from app.services.knowledge_documents import upsert_tenant_knowledge_document

router = APIRouter(prefix="/tenant", tags=["tenant"])


class FeatureFlagResponse(BaseModel):
    flag_key: str
    enabled: bool


class FeatureFlagUpdate(BaseModel):
    enabled: bool


class TenantLegalUpdate(BaseModel):
    inn: str = Field(min_length=10, max_length=14)


class KnowledgeDocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    body: str = Field(min_length=20, max_length=50000)
    visibility: str = Field(default="public", max_length=32)


def _require_tenant_admin(ctx: TenantContext) -> None:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Insufficient role")


@router.get("/feature-flags", response_model=list[FeatureFlagResponse])
def list_feature_flags(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> list[FeatureFlagResponse]:
    flags = db.query(FeatureFlag).filter(FeatureFlag.tenant_id == ctx.tenant_id).order_by(FeatureFlag.flag_key).all()
    return [FeatureFlagResponse(flag_key=f.flag_key, enabled=f.enabled) for f in flags]


@router.patch("/feature-flags/{flag_key}", response_model=FeatureFlagResponse)
def update_feature_flag(
    flag_key: str,
    body: FeatureFlagUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> FeatureFlagResponse:
    if ctx.role not in ("tenant_owner", "tenant_admin", "platform_admin"):
        raise HTTPException(status_code=403, detail="Insufficient role")
    flag = (
        db.query(FeatureFlag)
        .filter(FeatureFlag.tenant_id == ctx.tenant_id, FeatureFlag.flag_key == flag_key)
        .one_or_none()
    )
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    flag.enabled = body.enabled
    emit_event(
        db,
        tenant_id=ctx.tenant_id,
        event_type="feature.flag.updated",
        category="operational",
        source="tenant.feature_flags",
        payload={"flag_key": flag_key, "enabled": body.enabled},
    )
    db.commit()
    return FeatureFlagResponse(flag_key=flag.flag_key, enabled=flag.enabled)


@router.get("/me")
def tenant_me(db: Session = Depends(get_db), ctx: TenantContext = Depends(get_tenant_context_auth)) -> dict:
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    return {
        "tenant_id": str(ctx.tenant_id),
        "tenant_slug": ctx.tenant_slug,
        "tenant_name": tenant.name,
        "public_key": tenant.public_key,
        "user_id": str(ctx.user_id) if ctx.user_id else None,
        "role": ctx.role,
    }


@router.get("/party/lookup")
def tenant_party_lookup(
    inn: str = Query(..., min_length=10, max_length=14),
    force: bool = False,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """E1.12 — lookup legal entity by INN (DaData + PG cache)."""
    result = lookup_party_by_inn(
        db,
        inn,
        tenant_id=ctx.tenant_id,
        force=force,
    )
    if not result.get("ok") and result.get("error") == "invalid_inn":
        raise HTTPException(status_code=400, detail="INN must be 10 or 12 digits")
    db.commit()
    return result


@router.get("/party/suggest")
def tenant_party_suggest(
    q: str = Query(..., min_length=2, max_length=120),
    count: int = Query(default=5, ge=1, le=20),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """E1.14 — autocomplete legal entities by name or INN (DaData suggest)."""
    result = suggest_parties_by_query(
        db,
        q,
        tenant_id=ctx.tenant_id,
        count=count,
        source="tenant.party.suggest",
    )
    if not result.get("ok") and result.get("error") == "query_too_short":
        raise HTTPException(status_code=400, detail="Query must be at least 2 characters")
    db.commit()
    return result


@router.get("/legal")
def get_tenant_legal(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """E1.15 — read tenant legal profile from settings.legal."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    legal = (tenant.settings or {}).get("legal")
    return {"ok": True, "legal": legal}


@router.put("/legal")
def update_tenant_legal(
    body: TenantLegalUpdate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """E1.15 — enrich and store tenant.settings.legal from INN (onboarding / cabinet)."""
    _require_tenant_admin(ctx)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    old_legal = (tenant.settings or {}).get("legal")

    result = enrich_tenant_legal_from_inn(
        db,
        tenant,
        body.inn,
        tenant_id=ctx.tenant_id,
        source="tenant.legal.update",
    )
    if not result.get("enriched"):
        reason = result.get("reason")
        if reason == "invalid_inn":
            raise HTTPException(status_code=400, detail="INN must be 10 or 12 digits")
        raise HTTPException(status_code=422, detail=str(reason or "enrichment_failed"))

    write_audit(
        db,
        ctx,
        action="tenant.legal.update",
        resource=f"tenant:{tenant.id}",
        old_value={"legal": old_legal},
        new_value={"legal": result["legal"]},
    )
    kb_sync = sync_tenant_settings_for_ctx(db, ctx, source="tenant.legal.update")
    db.commit()
    return {"ok": True, "legal": result["legal"], "party_enriched": True, "knowledge_sync": kb_sync}


@router.get("/widget")
def tenant_widget_config(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """P2.3 — embed snippet for tenant site_key (public_key)."""
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    site_key = tenant.public_key
    return {
        "site_key": site_key,
        "api_base": "https://api.dlno.ru/v1/public/widget",
        "cdn_base": "https://cdn.dlno.ru/widget/v1",
        "embed_html": (
            f'<script src="https://cdn.dlno.ru/widget/v1/embed.js" '
            f'data-site-key="{site_key}" data-theme="auto" async></script>'
        ),
    }


@router.post("/knowledge/documents")
def create_knowledge_document(
    body: KnowledgeDocumentCreate,
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
) -> dict:
    """P2.2 — upload text KB document → brain search."""
    _require_tenant_admin(ctx)
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    visibility = body.visibility if body.visibility in ("public", "company") else "public"
    result = upsert_tenant_knowledge_document(
        db,
        tenant,
        title=body.title,
        body=body.body,
        visibility=visibility,
        source="tenant.knowledge.upload",
    )
    if not result.get("ok"):
        raise HTTPException(status_code=502, detail=result.get("detail") or result.get("reason") or "knowledge_failed")
    db.commit()
    return result


@router.get("/knowledge/documents")
def list_knowledge_documents(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context_auth),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """E3.7 — recent KB uploads for tenant cabinet."""
    from app.services.events import list_events_for_tenant

    _require_tenant_admin(ctx)
    events = list_events_for_tenant(
        db,
        ctx.tenant_id,
        event_type="knowledge.document_upserted",
        limit=limit,
    )
    items = []
    seen: set[str] = set()
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        doc_id = str(payload.get("document_id") or "")
        if doc_id and doc_id in seen:
            continue
        if doc_id:
            seen.add(doc_id)
        items.append(
            {
                "document_id": doc_id or None,
                "title": payload.get("title"),
                "source": payload.get("source") or event.payload.get("source") if isinstance(event.payload, dict) else None,
                "published_at": event.created_at.isoformat() if event.created_at else None,
            }
        )
    return {"items": items, "total": len(items)}
