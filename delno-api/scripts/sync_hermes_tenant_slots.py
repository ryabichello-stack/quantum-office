#!/usr/bin/env python3
"""Assign sticky Hermes slots and print container env that ops must apply.

Does NOT restart Docker — prints the DELNO_MCP_KEY_* values that must match
each hermes-tenant-* container so MCP calls stay in that tenant's space.

Usage (API container):
  python -m scripts.sync_hermes_tenant_slots
  python -m scripts.sync_hermes_tenant_slots --assign-demo delno-demo --assign-ql quantum-labs
"""

from __future__ import annotations

import argparse
import hashlib
import json

from app.core.db import SessionLocal
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.hermes_nous.runtime_pool import assign_isolated_runtime, list_runtime_slots
from app.services.mcp_gateway import ensure_mcp_api_key


def _sha8(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()[:8] if key else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assign-demo", default="delno-demo")
    parser.add_argument("--assign-ql", default="quantum-labs")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        slots = list_runtime_slots()
        print("slots", json.dumps(slots, ensure_ascii=False))
        mapping = [
            (args.assign_demo, "tenant-a"),
            (args.assign_ql, "tenant-b"),
        ]
        out = {}
        for slug, prefer in mapping:
            tenant = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
            if not tenant:
                print("missing_tenant", slug)
                continue
            ctx = TenantContext(tenant_id=tenant.id, tenant_slug=slug, role="tenant_owner")
            runtime = assign_isolated_runtime(db, ctx, prefer_slot=prefer)
            key = ensure_mcp_api_key(db, tenant)
            out[slug] = {
                "slot_id": runtime.get("slot_id"),
                "runtime_base_url": runtime.get("runtime_base_url"),
                "api_server_key_env": runtime.get("api_server_key_env"),
                "mcp_key_env": runtime.get("mcp_key_env"),
                "mcp_key_sha8": _sha8(key),
                "mcp_key": key,
            }
            print("assigned", slug, "→", runtime.get("slot_id"), "mcp_sha8", _sha8(key))
        print("APPLY_TO_HERMES_LAB_ENV=")
        if args.assign_demo in out:
            print(f"DELNO_MCP_KEY={out[args.assign_demo]['mcp_key']}")
        if args.assign_ql in out:
            print(f"DELNO_MCP_KEY_B={out[args.assign_ql]['mcp_key']}")
        print("JSON", json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "mcp_key"} for k, v in out.items()}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
