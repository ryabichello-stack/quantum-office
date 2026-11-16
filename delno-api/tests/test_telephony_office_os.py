"""Office OS telephony + Hermes setup/health (sqlite in-memory)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.call_job import CallJob  # noqa: F401
from app.models.call_session import CallSession  # noqa: F401
from app.models.channel_account import ChannelAccount  # noqa: F401
from app.models.conversation import Conversation, Message  # noqa: F401
from app.models.lead import Lead  # noqa: F401
from app.models.phone_number import PhoneNumber  # noqa: F401
from app.models.platform_event import PlatformEvent  # noqa: F401
from app.models.tenant import Tenant
from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import registry
from app.services import hermes_ops, phone_provision, telephony


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _tenant(db, slug="quantum-labs") -> Tenant:
    t = db.query(Tenant).filter(Tenant.slug == slug).one_or_none()
    if t:
        return t
    t = Tenant(id=uuid.uuid4(), slug=slug, name="Quantum Labs", settings={}, is_active=True)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_tools_registered():
    register_builtin_tools()
    names = {t.name for t in registry._tools.values()} if hasattr(registry, "_tools") else set()
    if not names:
        # fallback — list via catalog-like API
        from app.services.mcp_gateway import mcp_tools_catalog

        names = {t["name"] for t in mcp_tools_catalog()}
    for n in (
        "calls.list",
        "calls.dial",
        "phones.provision",
        "hermes.setup_status",
        "hermes.health",
    ):
        assert n in names


def test_provision_phone_and_inbound_session(db, monkeypatch):
    tenant = _tenant(db)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    out = phone_provision.provision_phone(db, ctx, e164="79699665899", label="ql-main")
    assert out["ok"] is True
    assert out["phone"]["e164"] == "+79699665899"
    assert out["phone"]["routing_config"]["voice_agent_slug"] == "default"
    assert out["phone"]["routing_config"]["trunk_id"] == "delno-quantum-labs"

    started = telephony.start_inbound_call(
        db,
        did="+79699665899",
        from_number="+79001112233",
        external_id="ast-1",
        trunk_id="delno-quantum-labs",
    )
    assert started["ok"] is True
    assert started["tenant_slug"] == "quantum-labs"
    assert started["voice_agent_slug"] == "default"
    sid = uuid.UUID(started["session"]["id"])

    monkeypatch.setattr(
        "app.operator.agent.run_operator_turn",
        lambda *a, **k: {"reply": "Мы делаем массовые выплаты.", "ok": True},
    )
    turn = telephony.frontline_turn(db, session_id=sid, text="Здравствуйте, что вы делаете?")
    assert turn["ok"] is True
    assert "выплат" in turn["reply"]

    monkeypatch.setattr(
        "app.services.telephony_brain_sync._brain_upsert",
        lambda *a, **k: {"ok": True, "document_id": "doc-test-call"},
    )

    ended = telephony.end_call(
        db,
        session_id=sid,
        transcript="user: hi\nagent: hello",
        summary="Короткий звонок про выплаты",
        outcome="completed",
        recording_url="https://cdn.example/rec.wav",
    )
    assert ended["ok"] is True
    assert ended["session"]["status"] == "ended"
    assert ended.get("brain", {}).get("ok") is True

    conv = db.query(Conversation).filter(Conversation.id == uuid.UUID(started["conversation_id"])).one()
    assert conv.status == "open"
    assert conv.meta.get("needs_review") is True
    assert conv.meta.get("visitor_phone") == "+79001112233"
    assert "выплат" in (conv.meta.get("summary") or "")
    assert conv.meta.get("recording_url") == "https://cdn.example/rec.wav"
    assert conv.meta.get("last_message_preview")

    from app.services.conversation_present import get_conversation_detail

    detail = get_conversation_detail(db, tenant.id, conv.id)
    assert detail is not None
    assert detail.get("summary")
    assert detail.get("call_session", {}).get("id") == str(sid)
    assert detail.get("call_session", {}).get("has_transcript") is True


def test_inbound_requires_trunk_and_voice_agent(db):
    tenant = _tenant(db)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    phone_provision.provision_phone(db, ctx, e164="+79699665899")

    assert telephony.start_inbound_call(
        db, did="+79699665899", from_number="+79001112233", trunk_id=""
    )["error"] == "trunk_not_provisioned"

    assert telephony.start_inbound_call(
        db, did="+79699665899", from_number="+79001112233", trunk_id="other-tenant"
    )["error"] == "trunk_not_provisioned"

    # Legacy mango-trunk alias still routes QL during dual-registration transition.
    via_legacy = telephony.start_inbound_call(
        db,
        did="+79699665899",
        from_number="+79001112233",
        trunk_id="mango-trunk",
        external_id="ast-legacy",
    )
    assert via_legacy["ok"] is True
    assert via_legacy["voice_agent_slug"] == "default"

    other = _tenant(db, slug="tenant-beta")
    other_ctx = TenantContext(tenant_id=other.id, tenant_slug=other.slug, role="tenant_owner")
    phone_provision.provision_phone(db, other_ctx, e164="+79990001122")
    phone = (
        db.query(PhoneNumber)
        .filter(PhoneNumber.tenant_id == other.id, PhoneNumber.e164 == "+79990001122")
        .one()
    )
    assert phone.routing_config["voice_agent_slug"].startswith("delno_")
    assert phone.routing_config["voice_agent_slug"] != "default"

    # Strip voice agent → fail closed (what made the live line Busy).
    cfg = dict(phone.routing_config or {})
    cfg.pop("voice_agent_slug", None)
    phone.routing_config = cfg
    db.commit()
    bad = telephony.start_inbound_call(
        db,
        did="+79990001122",
        from_number="+79001112233",
        trunk_id=phone.routing_config["trunk_id"],
    )
    assert bad["ok"] is False
    assert bad["error"] == "voice_agent_not_provisioned"


def test_outbound_job_and_claim(db):
    tenant = _tenant(db)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    phone_provision.provision_phone(db, ctx, e164="+79699665899")

    created = telephony.create_outbound_job(
        db, ctx, to_e164="+79005554433", script="Подтверди встречу на завтра", created_by="hermes"
    )
    assert created["ok"] is True
    assert created["job"]["status"] == "queued"
    assert db.query(CallJob).count() == 1

    claimed = telephony.claim_next_job(db)
    assert claimed is not None
    assert claimed["job"]["status"] == "in_progress"
    assert claimed["session"]["direction"] == "outbound"


def test_hermes_setup_and_health(db):
    tenant = _tenant(db)
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")

    status = hermes_ops.office_setup_status(db, ctx)
    assert status["ok"] is True
    assert status["setup_complete"] is False
    assert status["next_steps"] == []

    phone_provision.provision_phone(db, ctx, e164="+79699665899")
    hermes_ops.mark_setup_progress(db, ctx, kb_ready=True, note="vault imported")

    health = hermes_ops.office_health_report(db, ctx)
    assert health["ok"] is True
    assert "+79699665899" in health["telephony"]["active_dids"]
    assert health["message_ru"]


def test_health_skips_partial_login_when_sip_registered(db, monkeypatch):
    """Vault login without '/' must not unhealthy the office if Mango is Registered."""
    tenant = _tenant(db, slug="sip-partial-ok")
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    phone_provision.provision_phone(db, ctx, e164="+79991234567")
    settings = dict(tenant.settings or {})
    settings["secrets"] = {
        "mango_sip": {
            "login": "gask",
            "password": "x",
            "updated_at": "2026-11-13T00:00:00+00:00",
        }
    }
    tenant.settings = settings
    db.commit()

    monkeypatch.setattr(
        "app.services.sip_probe.probe_registration",
        lambda *_a, **_k: {
            "ok": True,
            "status": "registered",
            "reachable": True,
            "message_ru": "Registered",
        },
    )
    health = hermes_ops.office_health_report(db, ctx)
    codes = [a.get("code") for a in (health.get("alerts") or [])]
    assert "phone.sip_login_partial" not in codes
    assert health.get("healthy") is True


def test_health_partial_login_when_sip_not_registered(db, monkeypatch):
    tenant = _tenant(db, slug="sip-partial-bad")
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    phone_provision.provision_phone(db, ctx, e164="+79991234568")
    settings = dict(tenant.settings or {})
    settings["secrets"] = {
        "mango_sip": {
            "login": "gask",
            "password": "x",
            "updated_at": "2026-11-13T00:00:00+00:00",
        }
    }
    tenant.settings = settings
    db.commit()

    monkeypatch.setattr(
        "app.services.sip_probe.probe_registration",
        lambda *_a, **_k: {
            "ok": False,
            "status": "rejected",
            "reachable": True,
            "message_ru": "Rejected",
        },
    )
    health = hermes_ops.office_health_report(db, ctx)
    codes = [a.get("code") for a in (health.get("alerts") or [])]
    assert "phone.sip_login_partial" in codes
    assert health.get("healthy") is False
