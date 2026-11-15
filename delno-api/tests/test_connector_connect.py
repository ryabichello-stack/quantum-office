"""Calendar, mail, and video are connected only after a vault probe."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401 — register tables
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.operator.tools.builtin import UpdateTenantSettingsTool
from app.services.connector_connect import (
    ProbeError,
    catalog,
    connect_provider,
    google_oauth_start,
    link_status,
)
from app.services.connectors import list_tenant_connector_readiness


def _db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _ctx(db, slug: str) -> TenantContext:
    tenant = Tenant(slug=slug, name=slug, settings={"connectors": {"calendar": {"enabled": True}}}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantContext(tenant_id=tenant.id, tenant_slug=slug, role="tenant_owner")


def test_catalog_hints_are_anonymous():
    hints = " ".join(item["hint"] for item in catalog("calendar"))
    assert "ivan@example.ru" in hints
    assert "парол" in hints.lower()
    assert "ya29" not in hints
    assert "password=" not in hints.lower()


def test_enabled_flag_is_not_connected():
    db = _db()
    ctx = _ctx(db, "alpha")
    status = link_status(db, ctx, "calendar")
    assert status["status"] == "disconnected"
    rows = list_tenant_connector_readiness(db, ctx)
    calendar = next(row for row in rows if row["kind"] == "calendar")
    assert calendar["enabled"] is True
    assert calendar["usable"] is False
    assert calendar["connection_status"] == "disconnected"


def test_forged_settings_flag_is_ignored():
    db = _db()
    ctx = _ctx(db, "alpha")
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    tenant.settings = {
        "connectors": {"calendar": {"enabled": True}},
        "connector_links": {"calendar": {"status": "connected", "provider": "yandex", "message_ru": "вручную"}},
    }
    db.commit()
    assert link_status(db, ctx, "calendar")["status"] == "disconnected"


def test_calendar_connects_only_after_event_read(monkeypatch):
    db = _db()
    ctx_a = _ctx(db, "alpha")
    ctx_b = _ctx(db, "beta")
    secret = "app-password-not-for-logs"

    def _read(db, ctx, provider, creds):
        assert creds["password"] == secret
        assert ctx.tenant_slug == "alpha"
        return [{"summary": "A only", "start": "2026-11-15T10:00:00+03:00"}]

    monkeypatch.setattr("app.services.connector_connect.read_calendar_events", _read)
    result = connect_provider(
        db,
        ctx_a,
        kind="calendar",
        provider="yandex",
        login="ivan@example.ru",
        password=secret,
        calendar_url="https://caldav.yandex.ru/calendars/ivan/events-1/",
    )
    assert result["ok"] is True
    assert result["connection"]["status"] == "connected"
    assert secret not in str(result)
    assert link_status(db, ctx_b, "calendar")["status"] == "disconnected"
    rows = list_tenant_connector_readiness(db, ctx_a)
    assert next(row for row in rows if row["kind"] == "calendar")["usable"] is True


def test_failed_read_is_not_connected(monkeypatch):
    db = _db()
    ctx = _ctx(db, "alpha")
    secret = "app-password-not-for-logs"

    def _read(*_a, **_k):
        raise ProbeError("read_failed", "Не удалось прочитать события.")

    monkeypatch.setattr("app.services.connector_connect.read_calendar_events", _read)
    result = connect_provider(
        db,
        ctx,
        kind="calendar",
        provider="yandex",
        login="ivan@example.ru",
        password=secret,
        calendar_url="https://caldav.yandex.ru/calendars/ivan/events-1/",
    )
    assert result["ok"] is False
    assert result["connection"]["status"] == "failed"
    assert secret not in str(result)
    assert "прочитать" in result["message_ru"]


def test_internal_delno_calendar_reads_empty_list():
    db = _db()
    ctx = _ctx(db, "alpha")
    result = connect_provider(db, ctx, kind="calendar", provider="delno")
    assert result["ok"] is True
    assert result["connection"]["status"] == "connected"
    assert result["connection"]["probe"] == "calendar_events_read"


def test_mail_and_conference_need_a_probe(monkeypatch):
    db = _db()
    ctx = _ctx(db, "alpha")

    def _mail(*_a, **_k):
        raise ProbeError("auth_failed", "Почта не пустила: проверьте логин и пароль приложения.")

    monkeypatch.setattr("app.services.connector_connect.probe_mail_login", _mail)
    mail = connect_provider(
        db,
        ctx,
        kind="mail",
        provider="yandex",
        login="ivan@example.ru",
        password="mail-app-password",
    )
    assert mail["connection"]["status"] == "failed"
    assert "mail-app-password" not in str(mail)

    def _conf(*_a, **_k):
        return {"ok": True}

    monkeypatch.setattr("app.services.connector_connect.probe_conference", _conf)
    video = connect_provider(
        db,
        ctx,
        kind="conference",
        provider="yandex",
        password="telemost-token-value",
    )
    assert video["ok"] is True
    assert video["connection"]["status"] == "connected"
    assert "telemost-token-value" not in str(video)


def test_google_oauth_without_server_env(monkeypatch):
    db = _db()
    ctx = _ctx(db, "alpha")
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_REDIRECT_URI", raising=False)
    started = google_oauth_start(db, ctx)
    assert started["ok"] is False
    assert started["error"] == "oauth_not_configured"
    assert "authorize_url" not in started
    assert "CLIENT_SECRET" in started["message_ru"]


def test_settings_tool_cannot_flip_connection():
    db = _db()
    ctx = _ctx(db, "alpha")
    out = UpdateTenantSettingsTool().run(
        db,
        ctx,
        patch={"connector_links": {"calendar": {"status": "connected", "verified_by": "probe"}}},
    )
    assert out.ok is False
    assert link_status(db, ctx, "calendar")["status"] == "disconnected"
