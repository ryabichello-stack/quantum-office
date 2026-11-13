"""tenant → profile → single pool placement."""

from __future__ import annotations

import os

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
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL", "http://delno-hermes-pool:8642")
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "key-a-xxxxxxxxxxxxxxx")
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "256")
    monkeypatch.delenv("HERMES_ENABLE_EXTRA_WORKERS", raising=False)
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


def test_many_tenants_share_single_pool(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    profiles = []
    for i in range(5):
        t = _tenant(db, f"co-{i}")
        p = ensure_tenant_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
        profiles.append(p)
        assert p.status == "ready"
        assert p.worker_id == "pool"
        resolved = resolve_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
        assert resolved["base_url"].endswith(f"/p/{p.profile_id}")
        assert "workers/pool/profiles/" in (p.state_location or "")
    assert len({p.profile_id for p in profiles}) == 5
    assert {p.worker_id for p in profiles} == {"pool"}


def test_pool_exhausted_when_capacity_one(db, monkeypatch):
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp_x",
    )
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "1")
    ensure_worker_catalog(db)
    for slug in ("co-a", "co-b"):
        t = _tenant(db, slug)
        ensure_tenant_placement(
            db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
        )
    b = db.query(Tenant).filter(Tenant.slug == "co-b").one()
    pb = db.query(HermesProfile).filter(HermesProfile.tenant_id == b.id).one()
    assert pb.status == "provisioning"
    assert pb.worker_id is None
    with pytest.raises(PlacementError) as ei:
        resolve_placement(
            db, TenantContext(tenant_id=b.id, tenant_slug=b.slug, role="tenant_owner")
        )
    assert ei.value.code == "hermes_runtime_provisioning"


def test_legacy_ab_workers_marked_offline(db):
    # Seed legacy dogfood rows
    db.add(
        HermesWorker(
            worker_id="tenant-a",
            base_url="http://old-a:8642",
            api_server_key_env="HERMES_API_SERVER_KEY",
            status="ready",
            max_profiles=1,
        )
    )
    db.add(
        HermesWorker(
            worker_id="tenant-b",
            base_url="http://old-b:8642",
            api_server_key_env="HERMES_API_SERVER_KEY_B",
            status="ready",
            max_profiles=1,
        )
    )
    db.commit()
    rows = ensure_worker_catalog(db)
    assert {w.worker_id for w in rows} == {"pool"}
    legacy = db.query(HermesWorker).filter(HermesWorker.worker_id.in_(("tenant-a", "tenant-b"))).all()
    assert all(w.status == "offline" for w in legacy)


def test_worker_catalog_single_pool(db):
    rows = ensure_worker_catalog(db)
    assert len(rows) == 1
    assert rows[0].worker_id == "pool"
    assert (rows[0].max_profiles or 0) >= 1
    assert os.environ.get("HERMES_NOUS_RUNTIME_URL")
