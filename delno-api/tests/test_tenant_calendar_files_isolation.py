"""API picks vault credentials per tenant and never copies env secrets out."""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.calendar_accounts import credentials_for_calendar
from app.services.tenant_broker_access import TenantAccessError, prepare_broker_access
from app.services.tenant_vault import save_secret


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _tenant(db, slug: str, settings: dict | None = None) -> TenantContext:
    tenant = Tenant(slug=slug, name=slug, settings=settings or {}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")


def test_calendar_vault_is_per_tenant():
    db = _db()
    ctx_a = _tenant(db, "alpha")
    ctx_b = _tenant(db, "beta")
    save_secret(db, ctx_a, kind="calendar_google", password="token-aaa", foreign_consent=True)
    save_secret(db, ctx_b, kind="calendar_google", password="token-bbb", foreign_consent=True)
    assert credentials_for_calendar(db, ctx_a, "google") == {"token": "token-aaa"}
    assert credentials_for_calendar(db, ctx_b, "google") == {"token": "token-bbb"}
    assert "token-bbb" not in str(credentials_for_calendar(db, ctx_a, "google"))


def test_foreign_tenant_claim_rejected():
    db = _db()
    ctx_a = _tenant(db, "alpha")
    try:
        prepare_broker_access(
            db,
            ctx_a,
            kind="calendar",
            source="google",
            claimed_tenant="beta",
            config_base_url="http://calendar",
        )
        raise AssertionError("expected mismatch")
    except TenantAccessError as exc:
        assert exc.code == "tenant_mismatch"


def test_missing_tenant_rejected():
    db = _db()
    try:
        prepare_broker_access(db, None, kind="files", source="yadisk", config_base_url="http://files")
        raise AssertionError("expected tenant_required")
    except TenantAccessError as exc:
        assert exc.code == "tenant_required"


def test_live_cloud_without_vault_does_not_expose_env(monkeypatch):
    db = _db()
    ctx = _tenant(db, "alpha")
    monkeypatch.setenv("YADISK_TOKEN", "env-secret-value")
    monkeypatch.setenv("GOOGLE_CALENDAR_TOKEN", "env-cal-secret")
    try:
        prepare_broker_access(
            db,
            ctx,
            kind="files",
            source="yadisk",
            config_base_url="http://files",
        )
        raise AssertionError("expected tenant_credentials_required")
    except TenantAccessError as exc:
        assert exc.code == "tenant_credentials_required"
    try:
        prepare_broker_access(
            db,
            ctx,
            kind="calendar",
            source="google",
            config_base_url="http://calendar",
        )
        raise AssertionError("expected tenant_credentials_required")
    except TenantAccessError as exc:
        assert exc.code == "tenant_credentials_required"


def test_service_tenant_gets_flag_not_the_secret(monkeypatch):
    db = _db()
    ctx = _tenant(db, "quantum-labs", settings={"service_tenant": True})
    monkeypatch.setenv("YADISK_TOKEN", "env-secret-value")
    monkeypatch.setattr(
        "app.services.tenant_broker_access.get_settings",
        lambda: SimpleNamespace(
            service_tenant_slug="",
            calendar_base_url="http://calendar",
            files_base_url="http://files",
        ),
    )
    access = prepare_broker_access(
        db,
        ctx,
        kind="files",
        source="yadisk",
        config_base_url="http://files",
    )
    assert access["allow_env_fallback"] is True
    assert "env-secret-value" not in str(access)
    blob = access["credentials"]
    assert blob == {"allow_env_fallback": True}
    assert "token" not in blob


def test_marked_slug_is_service_tenant(monkeypatch):
    db = _db()
    ctx = _tenant(db, "office-ops")
    monkeypatch.setattr(
        "app.services.tenant_broker_access.get_settings",
        lambda: SimpleNamespace(
            service_tenant_slug="office-ops",
            calendar_base_url="",
            files_base_url="http://files",
        ),
    )
    access = prepare_broker_access(db, ctx, kind="calendar", source="mailru", config_base_url="http://calendar")
    assert access["allow_env_fallback"] is True
    other = _tenant(db, "customer")
    try:
        prepare_broker_access(db, other, kind="calendar", source="mailru", config_base_url="http://calendar")
        raise AssertionError("customer must not inherit env")
    except TenantAccessError as exc:
        assert exc.code == "tenant_credentials_required"
