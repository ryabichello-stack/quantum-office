#!/usr/bin/env python3
"""Place dogfood/combat tenants onto the single Hermes pool.

Usage (inside delno-api container with PYTHONPATH=/app):
  python scripts/bootstrap_hermes_placement.py
  python scripts/bootstrap_hermes_placement.py --also tenant-beta
"""

from __future__ import annotations

import argparse
import sys

from app.core.db import SessionLocal, Base, engine
import app.models  # noqa: F401
from app.models.tenant import Tenant
from app.services.hermes_nous.placement import (
    PlacementError,
    admin_assign_worker,
    ensure_tenant_placement,
    ensure_worker_catalog,
    list_placement_snapshot,
)
from app.core.tenant import TenantContext

POOL = "pool"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", default="delno-demo")
    parser.add_argument("--ql", default="quantum-labs")
    parser.add_argument(
        "--also",
        action="append",
        default=[],
        help="Extra tenant slug(s) to place on the pool",
    )
    parser.add_argument("--worker", default=POOL, help="Worker id (default: pool)")
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_worker_catalog(db)
        slugs = [args.demo, args.ql, *args.also]
        for slug in slugs:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
            if not tenant:
                print(f"skip missing tenant slug={slug}")
                continue
            try:
                profile = admin_assign_worker(
                    db, tenant_id=tenant.id, worker_id=args.worker
                )
                print(
                    f"ok {slug} → worker={profile.worker_id} profile={profile.profile_id} "
                    f"status={profile.status} home={profile.state_location}"
                )
            except PlacementError as exc:
                # Fallback: auto least-loaded (should be the only pool)
                ctx = TenantContext(
                    tenant_id=tenant.id, tenant_slug=tenant.slug, role="platform_admin"
                )
                try:
                    profile = ensure_tenant_placement(db, ctx)
                    print(
                        f"ok {slug} → worker={profile.worker_id} profile={profile.profile_id} "
                        f"status={profile.status} home={profile.state_location}"
                    )
                except PlacementError as exc2:
                    print(f"FAIL {slug}: {exc.code}/{exc2.code} {exc.detail}", file=sys.stderr)
                    return 1
        snap = list_placement_snapshot(db)
        print("snapshot_mode=", snap.get("mode"))
        print("snapshot_workers=", snap.get("workers"))
        print("snapshot_profiles_n=", len(snap.get("profiles") or []))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
