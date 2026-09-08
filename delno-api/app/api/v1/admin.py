from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import require_platform_admin
from app.core.db import get_db
from app.core.security import hash_password
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.admin import TenantCreateRequest, TenantResponse
from app.services.audit import write_audit
from app.services.events import emit_event
from app.services.party_enrichment import enrich_tenant_legal_from_inn, lookup_party_by_inn

router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_FLAGS = (
    "web_voice",
    "telegram",
    "max",
    "phone",
    "outbound_calls",
    "experimental_operator",
)


@router.get("/tenants", response_model=list[TenantResponse])
def list_tenants(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_platform_admin),
) -> list[TenantResponse]:
    tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).all()
    return [TenantResponse.from_orm_tenant(t) for t in tenants]


@router.post("/tenants", response_model=TenantResponse, status_code=201)
def create_tenant(
    body: TenantCreateRequest,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> TenantResponse:
    existing = db.query(Tenant).filter(Tenant.slug == body.slug).one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Tenant slug already exists: {body.slug}")

    tenant = Tenant(slug=body.slug, name=body.name, settings={"locale": "ru"})
    db.add(tenant)
    db.flush()

    for flag_key in DEFAULT_FLAGS:
        db.add(FeatureFlag(tenant_id=tenant.id, flag_key=flag_key, enabled=False))

    if body.owner_email:
        db.add(
            User(
                tenant_id=tenant.id,
                email=body.owner_email.lower(),
                role="tenant_owner",
                password_hash=hash_password(body.owner_password or "changeme123"),
            )
        )

    legal_enriched = False
    if body.legal_inn:
        enrich_result = enrich_tenant_legal_from_inn(
            db,
            tenant,
            body.legal_inn,
            tenant_id=tenant.id,
            source="admin.tenant.create",
        )
        legal_enriched = enrich_result.get("enriched") is True

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="tenant.created",
        category="domain",
        source="admin.tenants",
        payload={"slug": body.slug, "created_by": str(admin.id), "legal_enriched": legal_enriched},
    )

    from app.core.tenant import TenantContext

    write_audit(
        db,
        TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, user_id=admin.id, role=admin.role),
        action="admin.create_tenant",
        resource=f"tenant:{tenant.id}",
        new_value={"slug": tenant.slug, "name": tenant.name},
    )
    db.commit()
    db.refresh(tenant)
    return TenantResponse.from_orm_tenant(tenant)


@router.get("/party/lookup")
def admin_party_lookup(
    inn: str = Query(..., min_length=10, max_length=14),
    force: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(require_platform_admin),
) -> dict:
    """E1.12/E1.15 — platform admin party lookup (support UI)."""
    result = lookup_party_by_inn(db, inn, tenant_id=None, force=force)
    if not result.get("ok") and result.get("error") == "invalid_inn":
        raise HTTPException(status_code=400, detail="INN must be 10 or 12 digits")
    db.commit()
    return result
