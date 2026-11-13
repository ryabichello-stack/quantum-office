"""Resolve tenant + principal from inbound channel identifiers."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.principals import (
    PRINCIPAL_TEXT_GUEST,
    PRINCIPAL_TEXT_OWNER,
    PRINCIPAL_VOICE_PUBLIC,
    PRINCIPAL_WIDGET_GUEST,
    principal_for_public_channel,
)
from app.models.channel_account import ChannelAccount
from app.models.phone_number import PhoneNumber
from app.models.tenant import Tenant


@dataclass(frozen=True, slots=True)
class ChannelContext:
    tenant_id: UUID
    tenant_slug: str
    channel_type: str
    principal_id: str
    channel_account_id: UUID | None = None


def _active_tenant(db: Session, tenant_id: UUID) -> Tenant | None:
    return (
        db.query(Tenant)
        .filter(Tenant.id == tenant_id, Tenant.is_active.is_(True))
        .one_or_none()
    )


def resolve_by_slug(db: Session, slug: str) -> Tenant | None:
    return (
        db.query(Tenant)
        .filter(Tenant.slug == slug, Tenant.is_active.is_(True))
        .one_or_none()
    )


def resolve_by_public_key(db: Session, public_key: str) -> Tenant | None:
    return (
        db.query(Tenant)
        .filter(Tenant.public_key == public_key, Tenant.is_active.is_(True))
        .one_or_none()
    )


def resolve_by_phone_e164(db: Session, e164: str) -> ChannelContext | None:
    row = (
        db.query(PhoneNumber, Tenant)
        .join(Tenant, Tenant.id == PhoneNumber.tenant_id)
        .filter(PhoneNumber.e164 == e164, PhoneNumber.status == "active", Tenant.is_active.is_(True))
        .one_or_none()
    )
    if not row:
        return None
    phone, tenant = row
    return ChannelContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        channel_type="phone",
        principal_id=PRINCIPAL_VOICE_PUBLIC,
        channel_account_id=phone.channel_account_id,
    )


def resolve_by_messenger_token(db: Session, token: str, *, owner_context: bool = False) -> ChannelContext | None:
    accounts = (
        db.query(ChannelAccount)
        .filter(
            ChannelAccount.status == "active",
            ChannelAccount.type.in_(("telegram", "max")),
        )
        .all()
    )
    for ch in accounts:
        if (ch.credentials_encrypted or {}).get("bot_token") != token:
            continue
        tenant = _active_tenant(db, ch.tenant_id)
        if not tenant:
            continue
        principal = PRINCIPAL_TEXT_OWNER if owner_context else PRINCIPAL_TEXT_GUEST
        return ChannelContext(
            tenant_id=tenant.id,
            tenant_slug=tenant.slug,
            channel_type=ch.type,
            principal_id=principal,
            channel_account_id=ch.id,
        )
    return None


def resolve_widget(db: Session, public_key: str) -> ChannelContext | None:
    tenant = resolve_by_public_key(db, public_key)
    if not tenant:
        return None
    return ChannelContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        channel_type="web_widget",
        principal_id=PRINCIPAL_WIDGET_GUEST,
    )


def resolve_public_lead(db: Session, tenant_slug: str) -> ChannelContext | None:
    tenant = resolve_by_slug(db, tenant_slug)
    if not tenant:
        return None
    return ChannelContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        channel_type="website",
        principal_id=principal_for_public_channel("widget"),
    )
