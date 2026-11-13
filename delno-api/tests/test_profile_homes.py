"""Worker-visible Hermes profile homes (multiplex layout)."""

from __future__ import annotations

from pathlib import Path

from app.core.config import get_settings
from app.services.hermes_nous.profile_homes import (
    ensure_live_profile_home,
    live_profile_path,
    worker_bind_hint,
    worker_multiplex_root,
)


def test_ensure_live_profile_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_PROFILES_ROOT", str(tmp_path / "profiles"))
    get_settings.cache_clear()
    home = ensure_live_profile_home(
        "tenant_acme__company_main",
        worker_id="tenant-a",
        api_server_key="key-a-xxxxxxxxxxxxxxx",
    )
    assert home.exists()
    assert (home / "memories").is_dir()
    assert (home / ".delno_profile_id").read_text(encoding="utf-8").strip() == (
        "tenant_acme__company_main"
    )
    assert (home / ".env").read_text(encoding="utf-8").count("API_SERVER_KEY=") == 1
    assert live_profile_path("tenant_acme__company_main", worker_id="tenant-a") == home
    assert "workers/tenant-a/profiles/" in str(home)
    root = worker_multiplex_root("tenant-a")
    assert (root / "config.yaml").exists()
    hint = worker_bind_hint("tenant_acme__company_main", worker_id="tenant-a")
    assert hint["HERMES_WORKER_ID"] == "tenant-a"
    assert Path(hint["HERMES_HOME"]) == root
    assert hint["api_path_prefix"] == "/p/tenant_acme__company_main"
    get_settings.cache_clear()


def test_placement_uses_live_home(tmp_path, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.db import Base
    from app.core.tenant import TenantContext
    from app.models.tenant import Tenant
    from app.services.hermes_nous.placement import ensure_tenant_placement

    monkeypatch.setenv("TENANT_FILES_ROOT", str(tmp_path / "tenants"))
    monkeypatch.setenv("HERMES_PROFILES_ROOT", str(tmp_path / "profiles"))
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL", "http://delno-hermes-tenant-a:8642")
    monkeypatch.setenv("HERMES_NOUS_RUNTIME_URL_B", "http://delno-hermes-tenant-b:8642")
    monkeypatch.setenv("HERMES_API_SERVER_KEY", "key-a-xxxxxxxxxxxxxxx")
    monkeypatch.setenv("HERMES_API_SERVER_KEY_B", "key-b-xxxxxxxxxxxxxxx")
    monkeypatch.setenv("HERMES_WORKER_MAX_PROFILES", "64")
    get_settings.cache_clear()
    monkeypatch.setattr(
        "app.services.hermes_nous.placement.ensure_mcp_api_key",
        lambda db, tenant: "dmcp",
    )

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    t = Tenant(slug="acme", name="Acme", settings={})
    db.add(t)
    db.commit()
    db.refresh(t)
    profile = ensure_tenant_placement(
        db, TenantContext(tenant_id=t.id, tenant_slug=t.slug, role="tenant_owner")
    )
    assert "workers/" in profile.state_location
    assert "/profiles/" in profile.state_location
    assert Path(profile.state_location).exists()
    assert (Path(profile.state_location) / ".delno_profile_id").exists()
    db.close()
    get_settings.cache_clear()
