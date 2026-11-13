"""Office loop must read hermes_ops check id `kb` (PRODUCT_LOOP)."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.services.hermes_nous import onboarding as office_onboarding


def test_office_loop_kb_ok_uses_kb_check_id(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="loop-kb", name="Loop", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {"required_done": 1, "required_total": 7},
            "checks": {
                "kb": {"ok": True, "detail": {"ok": True}},
                "phone": {"ok": False},
                "mail": {"ok": False},
                "telephony_script": {"ok": True},
            },
        },
    )

    loop = office_onboarding.get_office_loop(db, ctx)
    assert loop["kb_ok"] is True
    assert loop["phase"] == "connectors"
    company_kb = next(s for s in loop["steps"] if s["id"] == "company_kb")
    assert company_kb["done"] is True
    connectors = next(s for s in loop["steps"] if s["id"] == "connectors")
    assert connectors["done"] is False
    # telephony_script must not inflate connector count
    assert loop["connectors_ready_count"] == 0
    db.close()
