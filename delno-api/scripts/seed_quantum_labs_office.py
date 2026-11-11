#!/usr/bin/env python3
"""Seed Quantum Labs dogfood tenant: ensure tenant + main DID for Office OS."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services import hermes_ops, phone_provision


DID = os.getenv("QL_DID", "+79699665899")


def main() -> int:
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.slug == "quantum-labs").one_or_none()
        if not tenant:
            tenant = Tenant(slug="quantum-labs", name="Quantum Labs", settings={}, is_active=True)
            db.add(tenant)
            db.commit()
            db.refresh(tenant)
            print("created tenant quantum-labs", tenant.id)
        else:
            print("tenant exists", tenant.id)

        ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
        out = phone_provision.provision_phone(db, ctx, e164=DID, label="ql-main")
        print("phone", out)
        hermes_ops.mark_setup_progress(db, ctx, kb_ready=True, note="dogfood seed")
        print("setup", hermes_ops.office_setup_status(db, ctx)["progress"])
        print("health", hermes_ops.office_health_report(db, ctx)["message_ru"])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
