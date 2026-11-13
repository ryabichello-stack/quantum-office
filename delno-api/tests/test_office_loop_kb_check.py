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
            "message_ru": "Давайте настроим офис. Следующий шаг: Телефония",
            "progress": {"required_done": 1, "required_total": 7},
            "checks": {
                "kb": {"ok": True, "detail": {"ok": True}},
                "phone": {"ok": False},
                "mail": {"ok": False},
                "telephony_script": {"ok": True},
            },
            "next_steps": [
                {
                    "id": "phone",
                    "title": "Телефония (линия)",
                    "hint": "DID + SIP в сейфе",
                    "status": "todo",
                    "check": {
                        "ok": False,
                        "detail": {
                            "active_dids": 0,
                            "sip_configured": False,
                            "registration_ok": False,
                        },
                    },
                }
            ],
        },
    )

    loop = office_onboarding.get_office_loop(db, ctx)
    assert loop["kb_ok"] is True
    assert loop["phase"] == "connectors"
    assert loop["setup_next"]["id"] == "phone"
    assert loop["setup_next"]["substep"] == "need_sip"
    assert "SIP" in (loop["ui"]["headline"] or "") or "Телефония" in (loop["ui"]["headline"] or "")
    assert "credentials.open_form" in (loop["ui"]["primary_cta"]["text"] or "")
    assert "импортировать kb" in (loop["ui"]["primary_cta"]["text"] or "").lower()
    company_kb = next(s for s in loop["steps"] if s["id"] == "company_kb")
    assert company_kb["done"] is True
    connectors = next(s for s in loop["steps"] if s["id"] == "connectors")
    assert connectors["done"] is False
    # telephony_script must not inflate connector count
    assert loop["connectors_ready_count"] == 0
    db.close()


def test_office_loop_phone_substep_need_did(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="loop-did", name="Loop", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {"required_done": 1, "required_total": 7},
            "checks": {"kb": {"ok": True}, "phone": {"ok": False}},
            "next_steps": [
                {
                    "id": "phone",
                    "title": "Телефония (линия)",
                    "hint": "DID + SIP",
                    "status": "todo",
                    "check": {
                        "ok": False,
                        "detail": {
                            "active_dids": 0,
                            "sip_configured": True,
                            "registration_ok": False,
                        },
                    },
                }
            ],
        },
    )
    loop = office_onboarding.get_office_loop(db, ctx)
    assert loop["setup_next"]["substep"] == "need_did"
    assert "DID" in (loop["ui"]["primary_cta"]["title"] or "")
    assert "phones.provision" in (loop["ui"]["primary_cta"]["text"] or "")
    assert "credentials.open_form" not in (loop["ui"]["primary_cta"]["text"] or "")
    db.close()


def test_office_loop_telephony_script_cta(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="loop-script", name="Loop", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {"required_done": 2, "required_total": 7},
            "checks": {
                "kb": {"ok": True},
                "phone": {"ok": True},
                "telephony_script": {"ok": False},
            },
            "next_steps": [
                {
                    "id": "telephony_script",
                    "title": "Сценарий секретаря",
                    "hint": "Надиктуйте сценарий",
                    "status": "todo",
                    "check": {"ok": False, "detail": {}},
                }
            ],
        },
    )
    loop = office_onboarding.get_office_loop(db, ctx)
    assert loop["setup_next"]["id"] == "telephony_script"
    assert "Сценарий" in (loop["ui"]["headline"] or "")
    assert "telephony.script" in (loop["ui"]["primary_cta"]["text"] or "")
    assert "импортировать kb" in (loop["ui"]["primary_cta"]["text"] or "").lower()
    db.close()


def test_office_loop_files_cta_opens_yadisk_form(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(id=uuid.uuid4(), slug="loop-files", name="Loop", settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    monkeypatch.setattr(
        "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
        lambda *_a, **_k: {
            "setup_complete": False,
            "message_ru": "next",
            "progress": {},
            "checks": {"kb": {"ok": True}, "phone": {"ok": True}, "files": {"ok": False, "optional": True}},
            "next_steps": [
                {
                    "id": "files",
                    "title": "Облако файлов",
                    "hint": "Яндекс/Mail/Drive",
                    "status": "todo",
                    "check": {"ok": False, "optional": True, "detail": {}},
                }
            ],
        },
    )
    loop = office_onboarding.get_office_loop(db, ctx)
    assert loop["setup_next"]["id"] == "files"
    assert "files_yadisk" in (loop["ui"]["primary_cta"]["text"] or "")
    assert "credentials.open_form" in (loop["ui"]["primary_cta"]["text"] or "")
    db.close()
