"""Seed default demo tenant and platform admin for local dev and first deploy."""

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.security import hash_password
from app.models.cms import CmsPage
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User

DEFAULT_FLAGS = (
    "web_voice",
    "telegram",
    "max",
    "phone",
    "outbound_calls",
    "experimental_operator",
)


def _ensure_flags(db: Session, tenant_id) -> None:
    for key in DEFAULT_FLAGS:
        exists = (
            db.query(FeatureFlag)
            .filter(FeatureFlag.tenant_id == tenant_id, FeatureFlag.flag_key == key)
            .one_or_none()
        )
        if not exists:
            db.add(FeatureFlag(tenant_id=tenant_id, flag_key=key, enabled=False))


def seed_demo_tenant() -> None:
    settings = get_settings()
    db: Session = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == settings.default_tenant_slug).one_or_none()
        if not tenant:
            tenant = Tenant(slug=settings.default_tenant_slug, name="DELNO Demo", settings={"locale": "ru"})
            db.add(tenant)
            db.flush()

        _ensure_flags(db, tenant.id)

        owner = db.query(User).filter(User.email == "owner@delno.one").one_or_none()
        if not owner:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email="owner@delno.one",
                    role="tenant_owner",
                    password_hash=hash_password("demo123456"),
                )
            )

        admin = db.query(User).filter(User.email == "admin@delno.one").one_or_none()
        if not admin:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email="admin@delno.one",
                    role="platform_admin",
                    password_hash=hash_password("admin123456"),
                )
            )

        db.commit()

        _seed_cms_pages(db)
        db.commit()
    finally:
        db.close()


def _seed_cms_pages(db: Session) -> None:
    if db.query(CmsPage).filter(CmsPage.slug == "faq", CmsPage.tenant_id.is_(None)).one_or_none():
        return
    db.add(
        CmsPage(
            slug="faq",
            title="FAQ",
            locale="ru",
            status="published",
            blocks={
                "sections": [
                    {"q": "Что такое DELNO?", "a": "ИИ-сотрудник первой линии для бизнеса."},
                    {"q": "Какие каналы?", "a": "Сайт, телефон, Telegram, MAX, email."},
                ]
            },
        )
    )
