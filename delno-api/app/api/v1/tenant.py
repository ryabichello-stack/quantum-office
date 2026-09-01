from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_tenant_context_auth
from app.core.db import get_db
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.services.events import emit_event
from app.services.party_enrichment import lookup_party_by_inn

router = APIRouter(prefix="/tenant", tags=["tenant"])


class FeatureFlagResponse(BaseModel):
    flag_key: str
    enabled: bool


class FeatureFlagUpdate(BaseModel):
    enabled: bool


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
def tenant_me(ctx: TenantContext = Depends(get_tenant_context_auth)) -> dict:
    return {
        "tenant_id": str(ctx.tenant_id),
        "tenant_slug": ctx.tenant_slug,
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
