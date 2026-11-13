"""tenant → profile → worker placement: multiplex pool, no silent fallback to worker A."""

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
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "key-a-xxxxxxxxxxxxxxx")
    monkeypatch.setenv("HERMES_API_SERVER_KEY_B", "key-b-xxxxxxxxxxxxxxx")
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "64")
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


def test_two_tenants_get_ready_profiles(db, monkeypatch):
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
    assert pa.status == "ready" and pb.status == "ready"
    assert pa.profile_id != pb.profile_id
    assert pa.worker_id in {"tenant-a", "tenant-b"}
    assert pb.worker_id in {"tenant-a", "tenant-b"}
    # Least-loaded packs onto A first when both empty → both may share A under multiplex.
    assert "workers/" in (pa.state_location or "")
    assert "/profiles/" in (pa.state_location or "")


def test_many_tenants_place_without_unavailable(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "8")
    ensure_worker_catalog(db)  # refresh capacity
    profiles = []
    for i in range(5):
        t = _tenant(db, f"co-{i}")
        p = ensure_tenant_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
        profiles.append(p)
        assert p.status == "ready", p.status
        assert p.worker_id
        resolved = resolve_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
        assert resolved["base_url"].endswith(f"/p/{p.profile_id}")
    assert len({p.profile_id for p in profiles}) == 5


def test_pool_exhausted_when_capacity_one(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "1")
    ensure_worker_catalog(db)
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
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "1")
    ensure_worker_catalog(db)
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
    assert os.environ.get("HERMES_NOUS_RUNTIME_URL")


def test_worker_catalog_seeded(db):
    rows = ensure_worker_catalog(db)
    assert len(rows) >= 2
    ids = {w.worker_id for w in rows}
    assert "tenant-a" in ids and "tenant-b" in ids
    assert all(isinstance(w, HermesWorker) for w in rows)
    assert all((w.max_profiles or 0) >= 1 for w in rows)
