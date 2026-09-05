"""P2.1 — self-service tenant registration."""

from __future__ import annotations

import re
import secrets
import uuid

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User
from app.services.events import emit_event
from app.services.party_enrichment import enrich_tenant_legal_from_inn
from app.services.tenant_settings_ingest import sync_tenant_settings_to_brain

DEFAULT_FLAGS = (
    "web_voice",
    "telegram",
    "max",
    "phone",
    "outbound_calls",
    "experimental_operator",
)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower().strip()).strip("-")
    base = base[:48] or "company"
    return base


def _unique_slug(db: Session, preferred: str) -> str:
    slug = preferred
    if not db.query(Tenant).filter(Tenant.slug == slug).one_or_none():
        return slug
    for _ in range(8):
        candidate = f"{preferred}-{secrets.token_hex(2)}"
        if not db.query(Tenant).filter(Tenant.slug == candidate).one_or_none():
            return candidate
    return f"{preferred}-{uuid.uuid4().hex[:6]}"


def register_tenant(
    db: Session,
    *,
    email: str,
    password: str,
    company_name: str,
    slug: str | None = None,
    inn: str | None = None,
) -> tuple[Tenant, User, dict]:
    """Create tenant + owner user. Returns (tenant, user, meta)."""
    normalized_email = email.strip().lower()
    if db.query(User).filter(User.email == normalized_email).one_or_none():
        raise ValueError("email_taken")

    preferred_slug = slugify(slug or company_name)
    tenant_slug = _unique_slug(db, preferred_slug)

    tenant = Tenant(
        slug=tenant_slug,
        name=company_name.strip(),
        settings={"locale": "ru", "onboarding": {"source": "self_service"}},
    )
    db.add(tenant)
    db.flush()

    for flag_key in DEFAULT_FLAGS:
        enabled = flag_key == "web_voice"
        db.add(FeatureFlag(tenant_id=tenant.id, flag_key=flag_key, enabled=enabled))

    user = User(
        tenant_id=tenant.id,
        email=normalized_email,
        role="tenant_owner",
        password_hash=hash_password(password),
    )
    db.add(user)
    db.flush()

    legal_enriched = False
    if inn:
        enrich_result = enrich_tenant_legal_from_inn(
            db,
            tenant,
            inn,
            tenant_id=tenant.id,
            source="auth.register",
        )
        legal_enriched = enrich_result.get("enriched") is True

    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="tenant.created",
        category="domain",
        source="auth.register",
        payload={
            "slug": tenant.slug,
            "email": normalized_email,
            "legal_enriched": legal_enriched,
            "self_service": True,
        },
    )
    emit_event(
        db,
        tenant_id=tenant.id,
        event_type="auth.register",
        category="operational",
        source="auth.register",
        payload={"user_id": str(user.id), "email": normalized_email},
    )

    kb_sync = sync_tenant_settings_to_brain(db, tenant, source="auth.register")
    kb_doc = _seed_welcome_knowledge(db, tenant)

    meta = {
        "legal_enriched": legal_enriched,
        "knowledge_sync": kb_sync,
        "welcome_document": kb_doc,
        "public_key": tenant.public_key,
    }
    return tenant, user, meta


def _seed_welcome_knowledge(db: Session, tenant: Tenant) -> dict:
    from app.services.knowledge_documents import upsert_tenant_knowledge_document

    body = (
        f"# {tenant.name}\n\n"
        "Добро пожаловать в DELNO. Это ваша стартовая база знаний — "
        "замените этот текст своими ответами о компании, услугах и ценах.\n\n"
        "## Частые вопросы\n"
        "- Чем занимается компания? — опишите продукт или услугу.\n"
        "- Как с вами связаться? — укажите телефон и email.\n"
    )
    return upsert_tenant_knowledge_document(
        db,
        tenant,
        title=f"{tenant.name} — база знаний",
        body=body,
        visibility="public",
        source="onboarding:welcome",
    )
