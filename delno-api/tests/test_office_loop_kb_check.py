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


def test_confirm_kb_draft_marks_settings_hermes(monkeypatch):
    """KB readiness must go through hermes_ops.mark_setup_progress → settings.hermes."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="loop-mark", name="Loop", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {},
            "checks": {"kb": {"ok": False}},
        },
    )
    calls: list[dict] = []

    def _mark(db_arg, ctx_arg, **kwargs):
        calls.append(kwargs)
        settings = dict(tenant.settings or {})
        hermes = dict(settings.get("hermes") or {})
        hermes["kb_ready"] = True
        hermes["company_profile_ready"] = True
        hermes["kb_source"] = "owner_upload"
        settings["hermes"] = hermes
        tenant.settings = settings
        db.add(tenant)
        db.commit()
        return {"setup_complete": False, "checks": {"kb": {"ok": True}}}

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.mark_setup_progress",
        _mark,
    )

    class _Ok:
        ok = True
        data = {"document_id": "d1"}
        message = "ok"

    import importlib

    reg_mod = importlib.import_module("app.operator.tools.registry")
    monkeypatch.setattr(reg_mod.registry, "get", lambda *_a, **_k: object())
    monkeypatch.setattr(reg_mod.registry, "run", lambda *_a, **_k: _Ok())
    monkeypatch.setattr("app.operator.tools.register_builtin_tools", lambda: None)

    office_onboarding.save_kb_draft(db, ctx, title="Профиль компании", body="Мы делаем X " * 5)
    out = office_onboarding.confirm_kb_draft(db, ctx)
    assert out["ok"] is True
    assert calls and calls[0].get("kb_ready") is True
    db.refresh(tenant)
    hermes = (tenant.settings or {}).get("hermes") or {}
    nous = (tenant.settings or {}).get("hermes_nous") or {}
    assert hermes.get("kb_ready") is True
    assert hermes.get("company_profile_ready") is True
    # Must NOT stash readiness only under hermes_nous
    assert nous.get("kb_ready") is not True
    db.close()


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
