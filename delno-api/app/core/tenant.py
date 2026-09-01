from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.models.tenant import Tenant


@dataclass(frozen=True, slots=True)
class TenantContext:
    """Request-scoped tenant identity. LLM tools receive this — never raw tenant_id from model."""

    tenant_id: UUID
    tenant_slug: str
    user_id: UUID | None = None


def resolve_tenant(
    db: Session,
    *,
    tenant_slug: str | None,
    api_key: str | None,
) -> Tenant:
    settings = get_settings()
    slug = tenant_slug or settings.default_tenant_slug

    if api_key and settings.api_key and api_key == settings.api_key:
        tenant = db.query(Tenant).filter(Tenant.slug == slug, Tenant.is_active.is_(True)).one_or_none()
        if tenant:
            return tenant

    tenant = db.query(Tenant).filter(Tenant.slug == slug, Tenant.is_active.is_(True)).one_or_none()
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant not found: {slug}")
    return tenant


def get_tenant_context(
    db: Session = Depends(get_db),
    x_tenant_slug: str | None = Header(default=None, alias="X-Tenant-Slug"),
    x_api_key: str | None = Header(default=None, alias="X-Api-Key"),
) -> TenantContext:
    tenant = resolve_tenant(db, tenant_slug=x_tenant_slug, api_key=x_api_key)
    return TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug)
