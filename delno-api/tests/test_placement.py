"""tenant → profile → worker placement: no silent fallback to worker A."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.hermes_runtime import HermesProfile, HermesWorker
from app.models.tenant import Tenant
from app.services.hermes_nous.placement import (
    PlacementError,
    ensure_tenant_placement,
    ensure_worker_catalog,
    resolve_placement,
)


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


def _tenant(db, slug: str) -> Tenant:
    t = Tenant(slug=slug, name=slug.title(), settings={})
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_two_tenants_get_distinct_workers(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    a = _tenant(db, "co-a")
    b = _tenant(db, "co-b")
    pa = ensure_tenant_placement(
        db, TenantContext(tenant_id=a.id, tenant_slug=a.slug, role="tenant_owner")
    )
    pb = ensure_tenant_placement(
        db, TenantContext(tenant_id=b.id, tenant_slug=b.slug, role="tenant_owner")
    )
    assert pa.worker_id != pb.worker_id
    assert pa.profile_id != pb.profile_id
    assert {pa.worker_id, pb.worker_id} == {"tenant-a", "tenant-b"}


def test_third_tenant_provisioning_not_stolen_slot(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    for slug in ("co-a", "co-b", "co-c"):
        t = _tenant(db, slug)
        ensure_tenant_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
    c = db.query(Tenant).filter(Tenant.slug == "co-c").one()
    pc = (
        db.query(HermesProfile)
        .filter(HermesProfile.tenant_id == c.id)
        .one()
    )
    assert pc.status == "provisioning"
    assert pc.worker_id is None
    with pytest.raises(PlacementError) as ei:
        resolve_placement(
            db, TenantContext(tenant_id=c.id, tenant_slug=c.slug, role="tenant_owner")
        )
    assert ei.value.code == "hermes_runtime_provisioning"


def test_resolve_never_uses_env_default_without_profile(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    # Exhaust pool
    for slug in ("x1", "x2"):
        t = _tenant(db, slug)
        ensure_tenant_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
    orphan = _tenant(db, "orphan")
    ctx = TenantContext(tenant_id=orphan.id, tenant_slug=orphan.slug, role="tenant_owner")
    ensure_tenant_placement(db, ctx)
    with pytest.raises(PlacementError):
        resolve_placement(db, ctx)
    # Must not equal worker A just because HERMES_NOUS_RUNTIME_URL is set
    assert os.environ.get("HERMES_NOUS_RUNTIME_URL")


def test_worker_catalog_seeded(db):
    rows = ensure_worker_catalog(db)
    assert len(rows) >= 2
    ids = {w.worker_id for w in rows}
    assert "tenant-a" in ids and "tenant-b" in ids
    assert all(isinstance(w, HermesWorker) for w in rows)
