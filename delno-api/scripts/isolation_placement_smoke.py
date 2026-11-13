#!/usr/bin/env python3
"""Offline isolation smoke: multiplex placement + run bindings (no live Hermes required).

Exit 0 only if:
  - three tenants all get ready placement with distinct profile homes
  - resolve_placement returns /p/<profile_id> URLs
  - capacity=1 still exhausts without stealing another tenant's slot
  - run binding scopes tools to the issuing tenant
"""

from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Allow running as `python scripts/...` from delno-api/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    import os

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.core.config import get_settings
    from app.core.db import Base
    from app.core.tenant import TenantContext
    from app.models.tenant import Tenant
    from app.services.hermes_nous.placement import (
        PlacementError,
        ensure_tenant_placement,
        ensure_worker_catalog,
        resolve_placement,
    )
    from app.services.hermes_nous.run_bindings import bind_run_token, lookup_binding

    with tempfile.TemporaryDirectory() as td:
        os.environ["TENANT_FILES_ROOT"] = str(Path(td) / "tenants")
        os.environ["HERMES_PROFILES_ROOT"] = str(Path(td) / "profiles")
        os.environ["HERMES_NOUS_RUNTIME_URL"] = "http://delno-hermes-tenant-a:8642"
        os.environ["HERMES_NOUS_RUNTIME_URL_B"] = "http://delno-hermes-tenant-b:8642"
        os.environ["HERMES_API_SERVER_KEY"] = "key-a-xxxxxxxxxxxxxxx"
        os.environ["HERMES_API_SERVER_KEY_B"] = "key-b-xxxxxxxxxxxxxxx"
        os.environ["HERMES_WORKER_MAX_PROFILES"] = "64"
        get_settings.cache_clear()

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()

        import app.services.hermes_nous.placement as placement_mod

        placement_mod.ensure_mcp_api_key = lambda db, tenant: "dmcp"  # type: ignore

        profiles = []
        for slug in ("iso-a", "iso-b", "iso-c"):
            t = Tenant(slug=slug, name=slug, settings={})
            db.add(t)
            db.commit()
            db.refresh(t)
            p = ensure_tenant_placement(
                db, TenantContext(tenant_id=t.id, tenant_slug=slug, role="tenant_owner")
            )
            profiles.append(p)
            print(f"tenant={slug} worker={p.worker_id} status={p.status} home={p.state_location}")

        if any(p.status != "ready" or not p.worker_id for p in profiles):
            print("FAIL: all three tenants must be ready under multiplex capacity")
            return 1
        if len({p.profile_id for p in profiles}) != 3:
            print("FAIL: profile_ids must be unique")
            return 1

        for p, slug in zip(profiles, ("iso-a", "iso-b", "iso-c")):
            resolved = resolve_placement(
                db,
                TenantContext(tenant_id=p.tenant_id, tenant_slug=slug, role="tenant_owner"),
            )
            if not str(resolved["base_url"]).endswith(f"/p/{p.profile_id}"):
                print(f"FAIL: expected /p/{p.profile_id} in {resolved['base_url']}")
                return 1
        print("OK: multiplex /p/<profile> URLs")

        # Capacity=1 still refuses to steal
        os.environ["HERMES_WORKER_MAX_PROFILES"] = "1"
        # Force catalog refresh on existing rows
        for w in ensure_worker_catalog(db):
            w.max_profiles = 1
            db.add(w)
        db.commit()
        # Fill both workers if not already full under cap=1
        # Existing 3 profiles may already exceed — clear extras' workers for a clean check
        for p in profiles[1:]:
            p.worker_id = None
            p.status = "provisioning"
            db.add(p)
        db.commit()
        # Keep first on A; place second on B; third must provision
        ensure_tenant_placement(
            db,
            TenantContext(
                tenant_id=profiles[0].tenant_id, tenant_slug="iso-a", role="tenant_owner"
            ),
            prefer_worker_id="tenant-a",
        )
        ensure_tenant_placement(
            db,
            TenantContext(
                tenant_id=profiles[1].tenant_id, tenant_slug="iso-b", role="tenant_owner"
            ),
            prefer_worker_id="tenant-b",
        )
        p3 = ensure_tenant_placement(
            db,
            TenantContext(
                tenant_id=profiles[2].tenant_id, tenant_slug="iso-c", role="tenant_owner"
            ),
        )
        if p3.status != "provisioning" or p3.worker_id is not None:
            print(f"FAIL: capacity=1 third should provision, got {p3.status}/{p3.worker_id}")
            return 1
        try:
            resolve_placement(
                db,
                TenantContext(
                    tenant_id=profiles[2].tenant_id, tenant_slug="iso-c", role="tenant_owner"
                ),
            )
            print("FAIL: resolve_placement must raise for provisioning tenant")
            return 1
        except PlacementError as exc:
            print(f"OK: resolve blocked under capacity=1 ({exc.code})")

        # Bindings
        os.environ["HERMES_WORKER_MAX_PROFILES"] = "64"
        t0 = db.query(Tenant).filter(Tenant.slug == "iso-a").one()
        exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        bind_run_token(
            db,
            tenant_id=t0.id,
            profile_id=profiles[0].profile_id,
            worker_id=profiles[0].worker_id or "tenant-a",
            run_id="delno_iso_1",
            session_id="iso-a:1",
            actor_user_id=None,
            agent_id="company_main",
            raw_token="dnrt_iso",
            tool_ids=["hermes.setup_status"],
            expires_at_unix=exp,
        )
        b = lookup_binding(db, run_id="delno_iso_1")
        assert b and b.tenant_id == t0.id
        print("OK: run binding scoped to iso-a")

        homes = {Path(p.state_location) for p in profiles[:2] if p.state_location}
        if len(homes) != 2 or not all(h.exists() for h in homes):
            print("FAIL: live profile homes missing/shared")
            return 1
        print("OK: distinct worker-visible profile homes")
        print("PASS isolation_placement_smoke")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
