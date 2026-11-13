#!/usr/bin/env python3
"""Seed Quantum Labs dogfood tenant: ensure tenant + main DID for Office OS."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.core.tenant import TenantContext
from app.models.feature_flag import FeatureFlag
from app.models.tenant import Tenant
from app.models.user import User
from app.services import connectors as conn_svc
from app.services import hermes_ops, phone_provision


DID = os.getenv("QL_DID", "+79699665899")
OWNER_EMAIL = os.getenv("QL_OWNER_EMAIL", "office@quantumlabs.ru")
OWNER_PASSWORD = os.getenv("QL_OWNER_PASSWORD", "hermes-ql-2026")
DOGFOOD_FLAGS = (
    "web_voice",
    "telegram",
    "max",
    "phone",
    "outbound_calls",
    "experimental_operator",
)


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

        connector_urls = {
            "mail": os.getenv("QL_MAIL_BASE_URL"),
            "calendar": os.getenv("QL_CALENDAR_BASE_URL"),
            "files": os.getenv("QL_FILES_BASE_URL"),
            "conference": os.getenv("QL_CONFERENCE_BASE_URL"),
            "outreach": os.getenv("QL_OUTREACH_BASE_URL", "http://qo-outreach:8012"),
        }
        for kind, base_url in connector_urls.items():
            c = conn_svc.update_tenant_connector(
                db,
                ctx,
                kind,
                enabled=True,
                base_url=base_url,
            )
            print("connector", kind, c.get("enabled"), c.get("configured"), c.get("error"))

        for key in DOGFOOD_FLAGS:
            row = (
                db.query(FeatureFlag)
                .filter(FeatureFlag.tenant_id == tenant.id, FeatureFlag.flag_key == key)
                .one_or_none()
            )
            if not row:
                db.add(FeatureFlag(tenant_id=tenant.id, flag_key=key, enabled=True))
            else:
                row.enabled = True
        db.commit()

        owner = db.query(User).filter(User.email == OWNER_EMAIL).one_or_none()
        if not owner:
            db.add(
                User(
                    tenant_id=tenant.id,
                    email=OWNER_EMAIL,
                    role="tenant_owner",
                    password_hash=hash_password(OWNER_PASSWORD),
                )
            )
            db.commit()
            print("owner created", OWNER_EMAIL)
        else:
            print("owner exists", OWNER_EMAIL)

        hermes_ops.mark_setup_progress(db, ctx, kb_ready=True, note="dogfood seed")
        print("setup", hermes_ops.office_setup_status(db, ctx)["progress"])
        print("health", hermes_ops.office_health_report(db, ctx)["message_ru"])
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
