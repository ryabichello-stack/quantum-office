"""Client-path matrix: onboarding order, secretary gate, meetings, tenant keys.

Providers (Mango, calendar, mail, video, messengers) are mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.adapters.connectors.base import ConnectorResult
from app.core.config import get_settings
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.call_session import CallSession  # noqa: F401
from app.models.phone_number import PhoneNumber
from app.models.platform_event import PlatformEvent  # noqa: F401
from app.models.tenant import Tenant
from app.models.tenant_voice_profile import TenantVoiceProfile  # noqa: F401
from app.models.usage_record import UsageRecord  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.services import billing, hermes_ops, telephony_script
from app.services.appointments import handle as handle_appointment
from app.services.ava_readiness import line_status, set_tenant_voice
from app.services.hermes_guide import coach_reply
from app.services.instrument_catalog import (
    Instrument,
    inventory_from_checks,
    register_instrument,
    setup_steps,
    stitch_offers,
    unregister_instrument,
)
from app.services.telephony_script import LINE_TOOLS_BEFORE_TEST


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


def _tenant(db, slug: str, **settings) -> Tenant:
    tenant = Tenant(slug=slug, name=slug, settings=settings or {}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def _ctx(tenant: Tenant) -> TenantContext:
    return TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")


def _ready_connectors():
    return [
        {"kind": "calendar", "usable": True, "enabled": True},
        {"kind": "mail", "usable": True, "enabled": True},
        {"kind": "conference", "usable": True, "enabled": True},
    ]


def test_catalog_order_is_kb_phone_script_then_office():
    ids = [s["id"] for s in setup_steps()]
    assert ids.index("kb") < ids.index("phone") < ids.index("telephony_script")
    assert ids.index("telephony_script") < ids.index("calendar")
    assert ids.index("calendar") < ids.index("mail") < ids.index("conference")


def test_future_channel_joins_registry_without_prompt_edit():
    register_instrument(
        Instrument(
            id="whatsapp",
            title="WhatsApp",
            hint="Можно сейчас или позже",
            optional=True,
            order=45,
            group="channel",
            connect_tool="credentials.open_form",
            plain_offer="WhatsApp можно подключить сейчас или позже.",
        )
    )
    try:
        ids = [s["id"] for s in setup_steps()]
        assert "whatsapp" in ids
        inv = inventory_from_checks({}, deferred=set())
        assert any(x["id"] == "whatsapp" for x in inv["missing"])
    finally:
        unregister_instrument("whatsapp")
        assert "whatsapp" not in {s["id"] for s in setup_steps()}


def test_stitch_after_phone_and_calendar():
    texts = [x["text"] for x in stitch_offers({"phone", "calendar"})]
    assert any("свободн" in t for t in texts)


def test_registered_does_not_offer_test_call_before_script(db):
    tenant = _tenant(db, "gate")
    ctx = _ctx(tenant)
    db.add(PhoneNumber(tenant_id=tenant.id, e164="+79990001122", status="active", routing_config={}))
    db.commit()
    with (
        patch("app.services.hermes_guide.phone_provision.list_phones") as phones,
        patch("app.services.hermes_guide.hermes_ops.office_setup_status") as setup,
        patch("app.services.hermes_guide.hermes_ops.office_health_report") as health,
        patch("app.services.hermes_guide.list_secret_status") as secrets,
        patch("app.services.sip_probe.probe_registration") as probe,
    ):
        phones.return_value = {"items": [{"e164": "+79990001122", "status": "active"}]}
        setup.return_value = {"message_ru": "Дальше сценарий", "checks": {}, "next_steps": []}
        health.return_value = {"message_ru": "Линия работает"}
        secrets.return_value = {"items": [{"kind": "mango_sip", "configured": True}]}
        probe.return_value = {"ok": True, "status": "registered", "message_ru": "ok"}
        out = coach_reply(db, ctx, "Телефон уже настроен?")
    assert out is not None
    reply = out["reply"].lower()
    assert "пробный звонок рано" in reply or "сначала" in reply
    assert "тестовый звонок" not in reply
    titles = [a["title"] for a in out.get("suggested_actions") or []]
    assert "Сценарий" in titles
    assert "Пробный звонок" not in titles
    probe.assert_called()
    assert probe.call_args.args[0] == "gate" or probe.call_args.args == ("gate",)


def test_test_call_only_after_script_cedar_and_tools(db):
    tenant = _tenant(db, "ready-line")
    ctx = _ctx(tenant)
    early = line_status(db, ctx)
    assert early["test_call_allowed"] is False
    telephony_script.save_telephony_script(
        db,
        ctx,
        script="Добрый день! Вы позвонили в компанию. Чем помочь? Запишу на встречу и пришлю письмо." * 2,
        publish_knowledge=False,
    )
    mid = line_status(db, ctx)
    assert mid["script_ready"] is True
    assert mid["test_call_allowed"] is False
    assert "send_email" in mid["missing_tools"] or "create_conference" in mid["missing_tools"]
    set_tenant_voice(db, ctx, "cedar")
    telephony_script.set_telephony_tools(db, ctx, tools=list(LINE_TOOLS_BEFORE_TEST))
    done = line_status(db, ctx)
    assert done["voice_ready"] is True
    assert done["tools_ready"] is True
    assert done["test_call_allowed"] is True
    assert "пробный" in done["message_ru"].lower()


def test_defer_calendar_then_come_back(db):
    tenant = _tenant(
        db,
        "later",
        hermes={"company_profile_ready": True, "telephony_script_ready": True},
        telephony={"script": "x" * 50, "tools": list(LINE_TOOLS_BEFORE_TEST)},
    )
    ctx = _ctx(tenant)
    db.add(PhoneNumber(tenant_id=tenant.id, e164="+79991112233", status="active", routing_config={}))
    db.commit()
    connectors = {
        "items": [
            {"kind": k, "enabled": False, "configured": True, "status": {"configured": True}}
            for k in ("mail", "calendar", "conference")
        ]
    }
    readiness = [
        {"kind": k, "enabled": False, "usable": False, "reason": "not_enabled"}
        for k in ("mail", "calendar", "conference")
    ]
    with (
        patch("app.services.hermes_ops.list_tenant_connectors", return_value=connectors),
        patch("app.services.hermes_ops.list_tenant_connector_readiness", return_value=readiness),
        patch("app.services.hermes_ops.list_secret_status", return_value={"items": [{"kind": "mango_sip", "configured": True}]}),
        patch("app.services.sip_probe.probe_registration", return_value={"ok": True, "status": "registered"}),
    ):
        hermes_ops.set_owner_goal(
            db, ctx,
            goal="Подключить календарь и почту для записи клиентов",
            requested_instruments=["calendar", "mail"],
        )
        first = hermes_ops.office_setup_status(db, ctx)
        assert first["checks"]["kb"]["ok"] is True
        assert first["checks"]["phone"]["ok"] is True
        assert first["next_steps"][0]["id"] == "calendar"
        hermes_ops.mark_setup_progress(db, ctx, defer_instrument="calendar")
        nxt = hermes_ops.office_setup_status(db, ctx)
        assert nxt["next_steps"][0]["id"] == "mail"
        assert "calendar" in nxt["deferred_instruments"]
        offer = [m for m in nxt["instruments"]["missing"] if m["id"] == "calendar"][0]
        assert offer["deferred"] is True
        assert "позже" in offer["offer_ru"]
        hermes_ops.mark_setup_progress(db, ctx, resume_instrument="calendar")
        back = hermes_ops.office_setup_status(db, ctx)
        assert back["next_steps"][0]["id"] == "calendar"


def test_mail_without_calendar_still_offers_mail_stitch_only_when_both(db):
    inv = inventory_from_checks(
        {"mail": {"ok": True}, "calendar": {"ok": False}, "phone": {"ok": True}},
    )
    connected = {x["id"] for x in inv["connected"]}
    assert connected == {"mail", "phone"}
    pair_texts = [s["text"] for s in inv["stitches"]]
    assert any("почт" in t.lower() and "телефон" in t.lower() for t in pair_texts)
    assert not any(s["a"] == "calendar" or s["b"] == "calendar" for s in inv["stitches"])


def test_two_companies_do_not_share_meetings_or_keys(db, tmp_path, monkeypatch):
    a = _tenant(db, "alpha", llm={"openai_api_key": "byok-alpha-secret"})
    b = _tenant(db, "beta")
    monkeypatch.setenv("HERMES_PROFILES_ROOT", str(tmp_path / "profiles"))
    monkeypatch.setenv("OPENAI_API_KEY", "platform-secret-should-not-leak")
    get_settings.cache_clear()
    from app.services.hermes_nous.placement import _llm_profile_kwargs
    from app.services.hermes_nous.profile_homes import ensure_live_profile_home

    kw_a = _llm_profile_kwargs(db, a)
    kw_b = _llm_profile_kwargs(db, b)
    assert kw_a["llm_key_source"] == "byok"
    assert kw_a["openai_api_key"] == "byok-alpha-secret"
    assert "platform-secret-should-not-leak" not in (kw_a["openai_api_key"] or "")
    assert kw_b["llm_key_source"] == "platform"
    assert kw_b["openai_api_key"] == "platform-secret-should-not-leak"
    home_a = ensure_live_profile_home(
        "tenant_alpha__company_main",
        worker_id="pool",
        api_server_key="a" * 16,
        openai_api_key=kw_a["openai_api_key"],
        llm_key_source=kw_a["llm_key_source"],
    )
    home_b = ensure_live_profile_home(
        "tenant_beta__company_main",
        worker_id="pool",
        api_server_key="b" * 16,
        openai_api_key=kw_b["openai_api_key"],
        llm_key_source=kw_b["llm_key_source"],
    )
    # Second ensure must not duplicate the managed key line.
    ensure_live_profile_home(
        "tenant_beta__company_main",
        worker_id="pool",
        api_server_key="b" * 16,
        openai_api_key=kw_b["openai_api_key"],
        llm_key_source=kw_b["llm_key_source"],
    )
    env_a = (home_a / ".env").read_text(encoding="utf-8")
    env_b = (home_b / ".env").read_text(encoding="utf-8")
    assert env_a.count("OPENAI_API_KEY=") == 1
    assert "OPENAI_API_KEY=byok-alpha-secret" in env_a
    assert "platform-secret-should-not-leak" not in env_a
    assert env_b.count("OPENAI_API_KEY=") == 1
    assert "OPENAI_API_KEY=platform-secret-should-not-leak" in env_b
    assert "byok-alpha-secret" not in env_b
    assert "DELNO_LLM_KEY_SOURCE=platform" in env_b
    assert "workers/pool/profiles/tenant_alpha__company_main" in str(home_a)
    assert home_a != home_b

    booked = handle_appointment(
        db,
        _ctx(a),
        "book_meeting",
        {"start": "2026-11-16T10:00:00", "email": "a@client.test", "title": "Созвон", "confirmed_by_caller": True},
        channel="voice",
    )
    assert booked["ok"] is True
    db.refresh(a)
    db.refresh(b)
    assert a.settings["appointments"][0]["email"] == "a@client.test"
    assert not (b.settings or {}).get("appointments")
    get_settings.cache_clear()


def test_internal_calendar_books_without_external_provider(db, monkeypatch):
    tenant = _tenant(db, "busy")
    ctx = _ctx(tenant)

    class _Busy:
        def check(self, **kwargs):
            return ConnectorResult(ok=True, configured=False, kind="calendar", data={"free": False})

        def suggest_slots(self, **kwargs):
            return ConnectorResult(
                ok=True,
                configured=False,
                kind="calendar",
                data={"suggestions": [{"start": "2026-11-16T15:00:00"}]},
            )

        def create_event(self, **kwargs):
            raise AssertionError("busy slot must not be booked")

    real = __import__("app.adapters.connectors", fromlist=["get_connector"]).get_connector

    def _get(kind):
        if kind == "calendar":
            return _Busy()
        return real(kind)

    monkeypatch.setattr("app.services.appointments.get_connector", _get)
    out = handle_appointment(
        db, ctx, "book_meeting", {"start": "2026-11-16T10:00:00", "email": "c@client.test"}
    )
    assert out["ok"] is True
    assert out.get("booked") is True
    assert out["appointment"]["sync_status"] == "local_only"
    assert (tenant.settings or {}).get("appointments")


def test_book_then_reschedule_confirm_cancel_same_record(db):
    tenant = _tenant(db, "flow")
    ctx = _ctx(tenant)
    booked = handle_appointment(
        db,
        ctx,
        "book_meeting",
        {
            "start": "2026-11-20T11:00:00",
            "email": "c@client.test",
            "title": "Демо",
            "phone": "+79001112233",
        },
        channel="telegram",
    )
    assert booked["booked"] is True
    assert booked["appointment"]["conference_url"] == ""
    assert "Почта не подключена" in booked["message_ru"]
    apt_id = booked["appointment"]["id"]
    moved = handle_appointment(
        db,
        ctx,
        "reschedule_meeting",
        {"appointment_id": apt_id, "start": "2026-11-21T12:00:00", "email": "c@client.test"},
    )
    assert moved["rescheduled"] is True
    confirmed = handle_appointment(db, ctx, "confirm_meeting", {"appointment_id": apt_id})
    assert confirmed["appointment"]["status"] == "confirmed"
    cancelled = handle_appointment(db, ctx, "cancel_meeting", {"appointment_id": apt_id})
    assert cancelled["appointment"]["status"] == "cancelled"


def test_internal_calendar_rejects_overlap_and_keeps_tenants_separate(db):
    first = _tenant(db, "calendar-first")
    second = _tenant(db, "calendar-second")
    params = {"start": "2026-12-10T10:00:00+03:00", "title": "Консультация"}
    a = handle_appointment(db, _ctx(first), "book_meeting", params)
    conflict = handle_appointment(db, _ctx(first), "book_meeting", params)
    b = handle_appointment(db, _ctx(second), "book_meeting", params)
    assert a["booked"] is True
    assert conflict["booked"] is False
    assert b["booked"] is True


def test_public_caller_cannot_cancel_other_phone_or_guess_id(db):
    tenant = _tenant(db, "calendar-identity")
    booked = handle_appointment(
        db, _ctx(tenant), "book_meeting",
        {"start": "2026-12-10T10:00:00+03:00", "phone": "+79001112233"},
    )
    from app.services.appointments import current_verified_phone

    public = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="public")
    token = current_verified_phone.set("+79009998877")
    try:
        denied = handle_appointment(
            db, public, "cancel_meeting",
            {"appointment_id": booked["appointment"]["id"], "phone": "+79001112233"},
            channel="voice",
        )
    finally:
        current_verified_phone.reset(token)
    assert denied["ok"] is False
    assert denied["error"] == "appointment_not_found_or_unverified"


def test_shared_phone_requires_appointment_choice(db):
    tenant = _tenant(db, "calendar-shared-phone")
    ctx = _ctx(tenant)
    for hour in (10, 12):
        assert handle_appointment(
            db, ctx, "book_meeting",
            {"start": f"2026-12-10T{hour}:00:00+03:00", "phone": "+79001112233"},
        )["booked"]
    from app.services.appointments import current_verified_phone

    token = current_verified_phone.set("+79001112233")
    try:
        ambiguous = handle_appointment(
            db, TenantContext(tenant.id, tenant.slug, role="public"),
            "cancel_meeting", {}, channel="voice",
        )
    finally:
        current_verified_phone.reset(token)
    assert ambiguous["error"] == "ambiguous_appointment"
    assert len(ambiguous["choices"]) == 2


def test_voice_and_messenger_share_booking(db, monkeypatch):
    from app.services import phone_provision, telephony, voice_tools

    tenant = _tenant(db, "shared")
    ctx = _ctx(tenant)
    phone_provision.provision_phone(db, ctx, e164="+79990001122")
    telephony_script.save_telephony_script(
        db,
        ctx,
        script="Добрый день! Секретарь компании. Запишу на встречу и пришлю письмо со временем." * 2,
        tools=list(LINE_TOOLS_BEFORE_TEST),
        publish_knowledge=False,
    )
    from app.services.sip_probe import trunk_id_for_tenant

    started = telephony.start_inbound_call(
        db,
        did="+79990001122",
        from_number="+79001110000",
        external_id="call-shared-1",
        trunk_id=trunk_id_for_tenant("shared"),
    )
    assert started["ok"] is True
    monkeypatch.setattr(
        "app.services.voice_tools.list_tenant_connector_readiness",
        lambda db, ctx: _ready_connectors(),
    )
    via_phone = voice_tools.dispatch(
        db,
        call_id="call-shared-1",
        action="book_meeting",
        params={
            "start": "2026-12-01T09:00:00",
            "email": "phone@client.test",
            "title": "Созвон",
            "confirmed_by_caller": True,
        },
    )
    assert via_phone["ok"] is True and via_phone["booked"] is True
    via_chat = handle_appointment(
        db,
        ctx,
        "meeting.book",
        {
            "start": "2026-12-02T09:00:00",
            "email": "chat@client.test",
            "title": "Из чата",
            "confirmed_by_caller": True,
        },
        channel="telegram",
    )
    assert via_chat["booked"] is True
    db.refresh(tenant)
    emails = {row["email"] for row in tenant.settings["appointments"]}
    assert emails == {"phone@client.test", "chat@client.test"}


def test_messenger_turn_calls_same_meeting_tool(db, monkeypatch):
    from app.operator.agent import run_operator_turn

    tenant = _tenant(db, "tg")
    ctx = _ctx(tenant)
    register_builtin_tools()
    state = {"n": 0}

    class _Provider:
        name = "openai"

        def chat_completion(self, **kwargs):
            state["n"] += 1
            if state["n"] == 1:
                return {
                    "ok": True,
                    "model": "gpt-6-luna",
                    "usage": {"prompt_tokens": 12, "completion_tokens": 4},
                    "data": {
                        "choices": [
                            {
                                "message": {
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "meeting_book",
                                                "arguments": json.dumps(
                                                    {
                                                        "start": "2026-12-03T10:00:00",
                                                        "email": "tg@client.test",
                                                        "title": "Чат",
                                                        "confirmed_by_caller": True,
                                                    }
                                                ),
                                            },
                                        }
                                    ],
                                }
                            }
                        ]
                    },
                }
            return {
                "ok": True,
                "model": "gpt-6-luna",
                "usage": {"prompt_tokens": 8, "completion_tokens": 6},
                "data": {"choices": [{"message": {"content": "Записала встречу и отправила письмо."}}]},
            }

    monkeypatch.setattr("app.operator.agent.get_model_provider", lambda: _Provider())
    monkeypatch.setattr("app.services.model_provider.get_model_provider", lambda: _Provider())
    out = run_operator_turn(db, ctx, message="Запишите меня на завтра в 10", channel="telegram")
    assert "встреч" in out["reply"].lower()
    names = [t.get("tool") for t in out.get("tool_calls") or []]
    assert "meeting.book" in names
    db.refresh(tenant)
    assert tenant.settings["appointments"][0]["channel"] == "telegram"
    rows = db.query(UsageRecord).filter(UsageRecord.tenant_id == tenant.id).all()
    assert any(r.metric == "llm.tokens" for r in rows)


def test_byok_is_metered_but_not_debited(db):
    tenant = _tenant(db, "byok")
    ctx = _ctx(tenant)
    billing.ensure_billing_defaults(db, tenant, grant_credits=100)
    db.commit()
    out = billing.record_llm_usage(
        db,
        ctx,
        prompt_tokens=1_000_000,
        completion_tokens=0,
        model="gpt-6-luna",
        key_source="byok",
        channel="hermes",
    )
    assert out["cost"] == 0
    assert abs(out["cost_usd"] - 0.10) < 1e-9
    db.refresh(tenant)
    assert billing.get_balance(tenant)["token_credits"] == 100
    turned = billing.record_hermes_turn(
        db, ctx, prompt_tokens=0, completion_tokens=0, duration_seconds=120, key_source="platform"
    )
    assert turned["minutes"]["quantity"] == 2.0


def test_gpt6_luna_price_and_lead_subject(monkeypatch):
    usd = billing.estimate_llm_vendor_usd(
        prompt_tokens=1_000_000, completion_tokens=1_000_000, model="gpt-6-luna"
    )
    assert abs(usd - 0.60) < 1e-9
    monkeypatch.setenv("LEAD_SMTP_HOST", "smtp.test")
    monkeypatch.setenv("LEAD_SMTP_PORT", "587")
    monkeypatch.setenv("LEAD_SMTP_USER", "u")
    monkeypatch.setenv("LEAD_SMTP_PASSWORD", "p")
    monkeypatch.setenv("LEAD_SMTP_FROM", "from@test")
    monkeypatch.setenv("LEAD_NOTIFY_TO", "to@test")
    get_settings.cache_clear()
    sent = {}

    class _Smtp:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            return None

        def login(self, *args):
            return None

        def send_message(self, message):
            sent["subject"] = message["Subject"]
            sent["body"] = message.get_content()

    monkeypatch.setattr("app.services.lead_email.smtplib.SMTP", _Smtp)
    from app.services.lead_email import _send_lead_email

    _send_lead_email(
        {
            "id": "1",
            "source": "site",
            "name": "Анна",
            "phone": "+7999",
            "email": "",
            "company": "",
            "website": "",
        }
    )
    assert sent["subject"] == "Заявка с Дельно (dlno.ru): новая заявка"
    assert sent["body"].splitlines()[0] == "Заявка с Дельно (dlno.ru)"
    get_settings.cache_clear()


def test_hermes_templates_use_gpt6_luna():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "hermes_runtime" / "templates"
    for name in ("home/config.yaml", "worker_root/config.yaml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "gpt-6-luna" in text
        assert "gpt-4.1-mini" not in text


def test_cta_names_propose_voice_and_tools():
    from app.services.hermes_nous.onboarding import _cta

    cta = _cta("connectors", True, {"id": "telephony_script", "title": "Сценарий", "hint": ""})
    text = cta["text"]
    assert "telephony.script_propose" in text
    assert "telephony.voice_set" in text
    assert "telephony.tools_set" in text
    assert "script_get" in text and "недостаточно" in text or "не ограничивайся" in text
