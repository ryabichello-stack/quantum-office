"""Sticky Hermes runtime assignment via placement map."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.runtime_pool import assign_isolated_runtime, list_runtime_slots


@pytest.fixture()
def db(tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("HERMES_PROFILES_ROOT", str(tmp_path / "hermes-profiles"))
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL", "http://delno-hermes-tenant-a:8642")
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL_B", "http://delno-hermes-tenant-b:8642")
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "key-a")
    monkeypatch.setenv("HERMES_API_SERVER_KEY_B", "key-b")
    get_settings.cache_clear()
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    get_settings.cache_clear()


def test_list_runtime_slots_default_two():
    slots = list_runtime_slots()
    assert len(slots) >= 2
    assert slots[0]["id"] == "tenant-a"
    assert slots[1]["id"] == "tenant-b"


def test_assign_isolated_runtime_sticky(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_test",
    )
    tenant = Tenant(slug="fresh-co", name="Fresh", settings={})
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    first = assign_isolated_runtime(db, ctx)
    assert first.get("ok") is True
    assert first["slot_id"] == "tenant-a"
    assert first["status"] == "ready"
    second = assign_isolated_runtime(db, ctx)
    assert second["slot_id"] == "tenant-a"
    assert second["profile_id"] == first["profile_id"]
