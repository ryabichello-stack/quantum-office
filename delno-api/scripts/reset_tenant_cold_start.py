#!/usr/bin/env python3
"""Hard-reset a tenant to empty cold-start (like a brand-new cabinet).

Usage (inside API container / venv):
  python -m scripts.reset_tenant_cold_start --slug quantum-labs
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import text

from app.core.db import SessionLocal
from app.models.tenant import Tenant


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
)


def reset_tenant_cold_start(slug: str, *, keep_user: bool = True) -> dict:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
        if not tenant:
            return {"ok": False, "error": "tenant_not_found", "slug": slug}
        tid = tenant.id

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
        return {
            "ok": True,
            "slug": slug,
            "tenant_id": str(tid),
            "deleted": deleted,
            "keep_user": keep_user,
        }
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True)
    args = parser.parse_args()
    out = reset_tenant_cold_start(args.slug)
    print(out)
    return 0 if out.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
