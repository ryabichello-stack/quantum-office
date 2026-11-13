#!/usr/bin/env python3
"""Offline isolation smoke: placement + run bindings (no live Hermes required).

Exit 0 only if:
  - two tenants get distinct workers/profiles
  - third tenant is provisioning (not stolen onto A)
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
    from app.models.hermes_runtime import HermesProfile
    from app.models.tenant import Tenant
    from app.services.hermes_nous.placement import PlacementError, ensure_tenant_placement, resolve_placement
    from app.services.hermes_nous.run_bindings import bind_run_token, lookup_binding

    with tempfile.TemporaryDirectory() as td:
        os.environ["TENANT_FILES_ROOT"] = str(Path(td) / "tenants")
        os.environ["HERMES_PROFILES_ROOT"] = str(Path(td) / "profiles")
        os.environ["HERMES_NOUS_RUNTIME_URL"] = "http://delno-hermes-tenant-a:8642"
        os.environ["HERMES_NOUS_RUNTIME_URL_B"] = "http://delno-hermes-tenant-b:8642"
        os.environ["HERMES_API_SERVER_KEY"] = "key-a"
        os.environ["HERMES_API_SERVER_KEY_B"] = "key-b"
        get_settings.cache_clear()

        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=engine)
        db = sessionmaker(bind=engine)()

        # Patch MCP key mint
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

        if profiles[0].worker_id == profiles[1].worker_id:
            print("FAIL: A and B share worker")
            return 1
        if profiles[2].status != "provisioning" or profiles[2].worker_id is not None:
            print("FAIL: third tenant should be provisioning without stolen worker")
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
            print(f"OK: resolve blocked ({exc.code})")

        # Bindings
        t0 = db.query(Tenant).filter(Tenant.slug == "iso-a").one()
        exp = int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())
        bind_run_token(
            db,
            tenant_id=t0.id,
            profile_id=profiles[0].profile_id,
            worker_id=profiles[0].worker_id,
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

        # Live homes exist and differ
        homes = {Path(p.state_location) for p in profiles[:2]}
        if len(homes) != 2 or not all(h.exists() for h in homes):
            print("FAIL: live profile homes missing/shared")
            return 1
        print("OK: distinct worker-visible profile homes")
        print("PASS isolation_placement_smoke")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
