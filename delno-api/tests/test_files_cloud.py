"""F3 — per-tenant cloud disk vault + Hermes coach cues."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.files_cloud import (
    cloud_status,
    credentials_for_source,
    detect_source_from_message,
    normalize_source,
)
from app.services.hermes_guide import _files_cloud_coach
from app.services.tenant_vault import credential_form_spec, save_secret


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _ctx(db) -> TenantContext:
    tenant = Tenant(slug="cloud-co", name="Cloud Co", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantContext(
        tenant_id=tenant.id,
        tenant_slug=tenant.slug,
        user_id=None,
        role="tenant_owner",
    )


def test_normalize_and_detect():
    assert normalize_source("Яндекс") == "yadisk"
    assert detect_source_from_message("Подключи Google Drive") == "gdrive"
    assert detect_source_from_message("подключи облако Mail.ru") == "mailru"


def test_yadisk_save_and_status():
    db = _db()
    ctx = _ctx(db)
    out = save_secret(db, ctx, kind="files_yadisk", password="y0_token_secret_value")
    assert out["ok"] is True
    assert "y0_token" not in str(out)
    st = cloud_status(db, ctx)
    yandex = next(i for i in st["items"] if i["source"] == "yadisk")
    assert yandex["ready"] is True
    creds = credentials_for_source(db, ctx, "yadisk")
    assert creds == {"token": "y0_token_secret_value"}


def test_gdrive_requires_foreign_consent():
    db = _db()
    ctx = _ctx(db)
    denied = save_secret(db, ctx, kind="files_gdrive", password="ya29.token")
    assert denied["ok"] is False
    assert denied["error"] == "foreign_consent_required"
    ok = save_secret(
        db,
        ctx,
        kind="files_gdrive",
        password="ya29.token",
        foreign_consent=True,
    )
    assert ok["ok"] is True
    creds = credentials_for_source(db, ctx, "gdrive")
    assert creds and creds["token"].startswith("ya29")


def test_hermes_opens_yadisk_form():
    db = _db()
    ctx = _ctx(db)
    reply = _files_cloud_coach(db, ctx, "Подключи Яндекс.Диск")
    assert reply is not None
    form = reply.get("pending_credential_form") or {}
    assert form.get("kind") == "files_yadisk"
    assert "Яндекс" in (reply.get("reply") or "")


def test_cloud_form_spec_foreign_flag():
    form = credential_form_spec("files_onedrive")
    assert form["require_foreign_consent"] is True
    assert form["login_optional"] is True
