#!/usr/bin/env python3
"""Migrate flat HERMES_PROFILES_ROOT/<profile_id> → workers/<worker>/profiles/<id>.

Safe to re-run. Does not start/stop Docker — caller restarts Hermes workers after.
Uses placement DB when available; otherwise leaves unassigned flat dirs in
unassigned/profiles/ for later ensure_tenant_placement.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        default="",
        help="HERMES_PROFILES_ROOT (default: env or /data/hermes-profiles)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import os

    root = Path(
        args.root
        or os.environ.get("HERMES_PROFILES_ROOT")
        or "/data/hermes-profiles"
    )
    if not root.is_dir():
        print(f"missing root {root}", file=sys.stderr)
        return 1

    # Optional DB mapping profile_id → worker_id
    mapping: dict[str, str] = {}
    try:
        from app.core.db import SessionLocal
        import app.models  # noqa: F401
        from app.models.hermes_runtime import HermesProfile

        db = SessionLocal()
        try:
            for p in db.query(HermesProfile).all():
                if p.profile_id and p.worker_id:
                    mapping[p.profile_id] = p.worker_id
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001 — offline migrate still useful
        print(f"note: no DB mapping ({exc}); using unassigned/ for unknowns")

    moved = 0
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        name = child.name
        if name in {"workers", "unassigned"}:
            continue
        if name.startswith("."):
            continue
        # Only migrate dirs that look like company profiles
        if not (child / ".delno_profile_id").exists() and not (child / "config.yaml").exists():
            continue
        worker_id = mapping.get(name) or "unassigned"
        if worker_id == "unassigned":
            dest = root / "unassigned" / "profiles" / name
        else:
            dest = root / "workers" / worker_id / "profiles" / name
        print(f"{'DRY ' if args.dry_run else ''}move {child} → {dest}")
        if args.dry_run:
            moved += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            print(f"  skip exists {dest}")
            continue
        shutil.move(str(child), str(dest))
        moved += 1

    # Seed worker roots for known workers
    for wid in sorted(set(mapping.values()) | {"tenant-a", "tenant-b"}):
        wroot = root / "workers" / wid
        (wroot / "profiles").mkdir(parents=True, exist_ok=True)
        cfg = wroot / "config.yaml"
        if not cfg.exists() and not args.dry_run:
            cfg.write_text(
                "gateway:\n  multiplex_profiles: true\n  auto_multiplex_migration: true\n"
                "mcp_servers: {}\n",
                encoding="utf-8",
            )
    print(f"done moved={moved} mapped={len(mapping)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
