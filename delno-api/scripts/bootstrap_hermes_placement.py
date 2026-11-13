#!/usr/bin/env python3
"""Pin dogfood tenants onto multiplex pool workers (platform bootstrap).

Usage (inside delno-api container or with DATABASE_URL):
  python scripts/bootstrap_hermes_placement.py --demo delno-demo --ql quantum-labs
  python scripts/bootstrap_hermes_placement.py --also tenant-beta

Many tenants may share a worker (HERMES_WORKER_MAX_PROFILES). Prefer spreading
demo/QL across A/B for dogfood isolation demos.
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--demo", default="delno-demo")
    parser.add_argument("--ql", default="quantum-labs")
    parser.add_argument("--demo-worker", default="tenant-a")
    parser.add_argument("--ql-worker", default="tenant-b")
    parser.add_argument(
        "--also",
        action="append",
        default=[],
        help="Extra tenant slug(s) to auto-place on least-loaded worker",
    )
    args = parser.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_worker_catalog(db)
        mapping = (
            (args.demo, args.demo_worker),
            (args.ql, args.ql_worker),
        )
        for slug, worker_id in mapping:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
            if not tenant:
                print(f"skip missing tenant slug={slug}")
                continue
            try:
                profile = admin_assign_worker(db, tenant_id=tenant.id, worker_id=worker_id)
                print(
                    f"ok {slug} → worker={profile.worker_id} profile={profile.profile_id} "
                    f"status={profile.status} home={profile.state_location}"
                )
            except PlacementError as exc:
                print(f"FAIL {slug}: {exc.code} {exc.detail}", file=sys.stderr)
                return 1
        for slug in args.also:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
            if not tenant:
                print(f"skip missing tenant slug={slug}")
                continue
            ctx = TenantContext(
                tenant_id=tenant.id, tenant_slug=tenant.slug, role="platform_admin"
            )
            try:
                profile = ensure_tenant_placement(db, ctx)
                print(
                    f"ok {slug} → worker={profile.worker_id} profile={profile.profile_id} "
                    f"status={profile.status} home={profile.state_location}"
                )
            except PlacementError as exc:
                print(f"FAIL {slug}: {exc.code} {exc.detail}", file=sys.stderr)
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
