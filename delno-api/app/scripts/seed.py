"""Seed default demo tenant for local dev and first deploy."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.tenant import Tenant
from app.models.user import User


def seed_demo_tenant() -> None:
    settings = get_settings()
    db: Session = SessionLocal()
    try:
        existing = db.query(Tenant).filter(Tenant.slug == settings.default_tenant_slug).one_or_none()
        if existing:
            return
        tenant = Tenant(slug=settings.default_tenant_slug, name="DELNO Demo", settings={"locale": "ru"})
        db.add(tenant)
        db.flush()
        db.add(User(tenant_id=tenant.id, email="owner@delno.one", role="tenant_owner"))
        db.commit()
    finally:
        db.close()
