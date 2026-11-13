#!/usr/bin/env python3
"""Hard-reset a tenant to empty cold-start (like a brand-new cabinet).

Keeps the tenant row + login users + billing/mcp_api_key/locale.
Wipes office data, Hermes profile home, and re-places on the combat pool.

Usage (inside API container):
  PYTHONPATH=/app python /app/scripts/reset_tenant_cold_start.py --slug quantum-labs
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from sqlalchemy import text

from app.core.db import SessionLocal
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.placement import (
    ensure_tenant_placement,
    ensure_worker_catalog,
    profile_id_for_tenant,
)
from app.services.hermes_nous.profile_homes import live_profile_path, profiles_root
from app.services.hermes_nous.provision import hermes_home_path


# Child tables first. Unknown tables are skipped.
_DELETE_SQL = (
    "delete from agent_steps where run_id in (select id from agent_runs where tenant_id = :t)",
    "delete from agent_runs where tenant_id = :t",
    "delete from agent_tasks where tenant_id = :t",
    "delete from messages where tenant_id = :t",
    "delete from conversations where tenant_id = :t",
    "delete from channel_accounts where tenant_id = :t",
    "delete from phone_numbers where tenant_id = :t",
    "delete from call_jobs where tenant_id = :t",
    "delete from call_sessions where tenant_id = :t",
    "delete from leads where tenant_id = :t",
    "delete from platform_events where tenant_id = :t",
    "delete from audit_logs where tenant_id = :t",
    "delete from tenant_secrets where tenant_id = :t",
    "delete from usage_events where tenant_id = :t",
    "delete from usage_records where tenant_id = :t",
    "delete from onboarding_uploads where tenant_id = :t",
    "delete from tenant_voice_profiles where tenant_id = :t",
    "delete from feature_flags where tenant_id = :t",
    "delete from hermes_run_bindings where tenant_id = :t",
    "delete from hermes_profiles where tenant_id = :t",
)


def _wipe_dir(path: Path) -> bool:
    if not path.exists():
        return False
    shutil.rmtree(path, ignore_errors=True)
    return True


def reset_tenant_cold_start(slug: str, *, keep_user: bool = True, replace_hermes: bool = True) -> dict:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
        if not tenant:
            return {"ok": False, "error": "tenant_not_found", "slug": slug}
        tid = tenant.id
        pid = profile_id_for_tenant(tenant.slug)

        deleted: dict[str, int] = {}
        for sql in _DELETE_SQL:
            label = sql.split(" from ", 1)[1].split(" ", 1)[0]
            try:
                res = db.execute(text(sql), {"t": tid})
                db.commit()
                deleted[label] = int(res.rowcount or 0)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                deleted[label] = -1
                print(f"skip {label}: {exc}", file=sys.stderr)

        prev = dict(tenant.settings) if isinstance(tenant.settings, dict) else {}
        keep = {k: prev[k] for k in ("billing", "mcp_api_key", "locale") if k in prev}
        tenant.settings = {
            **keep,
            "locale": keep.get("locale") or "ru",
            "onboarding": {"source": "reset", "cold_start": True},
            "hermes": {
                "kb_ready": False,
                "company_profile_ready": False,
                "telephony_script_ready": False,
            },
            "connectors": {},
            "hermes_nous": {"office_loop": {"phase": "welcome"}},
        }
        db.add(tenant)
        db.commit()

        wiped_paths: list[str] = []
        # API-side hermes skeleton under tenant files
        api_home = hermes_home_path(tid)
        if _wipe_dir(api_home):
            wiped_paths.append(str(api_home))
        # Any leftover under tenant root except keep structure
        tenant_root = Path(str(api_home).rsplit("/hermes", 1)[0]) if "/hermes" in str(api_home) else None
        if tenant_root and tenant_root.is_dir():
            for child in list(tenant_root.iterdir()):
                if child.name == "hermes":
                    continue
                if _wipe_dir(child) or (child.is_file() and child.unlink(missing_ok=True) is None):
                    wiped_paths.append(str(child))

        # Worker-visible multiplex homes (pool + any legacy worker trees)
        for wid in ("pool", "tenant-a", "tenant-b", None):
            try:
                home = live_profile_path(pid, worker_id=wid)
            except Exception:  # noqa: BLE001
                continue
            if _wipe_dir(home):
                wiped_paths.append(str(home))
        # Legacy flat path
        flat = profiles_root() / pid
        if _wipe_dir(flat):
            wiped_paths.append(str(flat))

        placement = None
        if replace_hermes:
            ensure_worker_catalog(db)
            ctx = TenantContext(
                tenant_id=tid, tenant_slug=tenant.slug, role="platform_admin"
            )
            profile = ensure_tenant_placement(db, ctx)
            placement = {
                "worker_id": profile.worker_id,
                "profile_id": profile.profile_id,
                "status": profile.status,
                "state_location": profile.state_location,
            }

        return {
            "ok": True,
            "slug": slug,
            "tenant_id": str(tid),
            "deleted": deleted,
            "wiped_paths": wiped_paths,
            "placement": placement,
            "keep_user": keep_user,
            "note": "login users kept; cabinet is empty cold-start (welcome)",
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    parser.add_argument(
        "--no-replace-hermes",
        action="store_true",
        help="Do not re-create Hermes profile/placement after wipe",
    )
    args = parser.parse_args()
    out = reset_tenant_cold_start(
        args.slug, replace_hermes=not args.no_replace_hermes
    )
    print(out)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
