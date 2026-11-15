"""Onboarding fixes 2026-11-15: Mango login formats, SIP outcome to Hermes,
live progress of in-API tools, agent_runs closing, honest «номер» wording."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.agent_task import AgentRun
from app.models.phone_number import PhoneNumber  # noqa: F401
from app.models.platform_event import PlatformEvent  # noqa: F401
from app.models.tenant import Tenant
from app.models.tenant_voice_profile import TenantVoiceProfile  # noqa: F401
from app.services.ava_readiness import line_status
from app.services.sip_probe import classify_sip_outcome, normalize_mango_login, parse_mango_login


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _ctx(db, slug="acme") -> TenantContext:
    tenant = Tenant(slug=slug, name=slug, settings={}, is_active=True)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return TenantContext(tenant_id=tenant.id, tenant_slug=slug, role="tenant_owner")


@pytest.mark.parametrize(
    "raw",
    [
        "123456789/ivan",
        "ivan@vpbx123456789.mangosip.ru",
        "sip:ivan@vpbx123456789.mangosip.ru",
        "SIP:ivan@VPBX123456789.MANGOSIP.RU:5060",
        " ivan@vpbx123456789.mangosip.ru ",
    ],
)
def test_mango_login_formats_accepted(raw):
    parsed = parse_mango_login(raw)
    assert parsed["error"] is None
    assert parsed["account"] == "123456789"
    assert parsed["employee"].lower() == "ivan"
    assert normalize_mango_login(raw).lower() == "123456789/ivan" or "/" in normalize_mango_login(raw)


@pytest.mark.parametrize("raw", ["ivan", "ivan@mangosip.ru", "12/ivan"])
def test_mango_login_incomplete_rejected(raw):
    assert parse_mango_login(raw)["error"] == "login_must_be_account_slash_employee"


def test_apply_sends_normalized_login_to_helper(monkeypatch):
    from app.services import sip_probe

    seen = {}

    def fake_apply(url, *, tenant_slug, login, password, did=None):
        seen["login"] = login
        return {"ok": True}

    monkeypatch.setenv("ASTERISK_SIP_APPLY_URL", "http://helper.invalid")
    monkeypatch.setattr(sip_probe, "_apply_via_http", fake_apply)
    sip_probe.apply_mango_sip(tenant_slug="acme", login="ivan@vpbx123456789.mangosip.ru", password="x" * 12)
    assert seen["login"] == "123456789/ivan"


def test_classify_outcomes_plain_words():
    fmt = classify_sip_outcome({"ok": False, "error": "login_must_be_account_slash_employee"})
    assert fmt["code"] == "format" and "ivan@vpbx123456789.mangosip.ru" in fmt["message_ru"]
    rej = classify_sip_outcome({"ok": False, "registration": {"status": "rejected"}})
    assert rej["code"] == "rejected"
    assert "SIP-пароль" in rej["message_ru"] and "личного кабинета не подойдёт" in rej["message_ru"]
    assert classify_sip_outcome({"ok": True})["code"] == "registered"
    assert classify_sip_outcome({"ok": False, "skipped": True})["code"] == "saved_only"
    assert classify_sip_outcome({"ok": False})["code"] == "not_registered"


def test_vault_save_normalizes_login_and_remembers_outcome(db):
    from app.services import tenant_vault

    ctx = _ctx(db)
    with patch(
        "app.services.sip_probe.after_vault_sip_save",
        return_value={"ok": False, "registration": {"status": "rejected"}},
    ):
        out = tenant_vault.save_secret(
            db, ctx, kind="mango_sip", login="ivan@vpbx123456789.mangosip.ru", password="p" * 12
        )
    assert out["ok"] is True
    assert out["sip_outcome"]["code"] == "rejected"
    assert out.get("pending_credential_form")
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    assert tenant.settings["secrets"]["mango_sip"]["login"] == "123456789/ivan"
    assert tenant.settings["telephony_sip_last"]["code"] == "rejected"
    assert "p" * 12 not in str(out)


def test_mango_form_has_anonymized_field_hints():
    from app.services.tenant_vault import credential_form_spec

    form = credential_form_spec("mango_sip")
    login = next(f for f in form["fields"] if f["name"] == "login")
    pw = next(f for f in form["fields"] if f["name"] == "password")
    assert "ivan@vpbx123456789.mangosip.ru" in login["placeholder"]
    assert "123456789/ivan" in login["help"]
    assert "Сотрудники" in pw["help"] and "личного кабинета не подойдёт" in pw["help"]


def test_facts_block_mentions_last_sip_result():
    from app.services.hermes_nous.bridge import _office_facts_block

    text = _office_facts_block({"sip_last": {"code": "rejected", "message_ru": "не тот пароль"}})
    assert "последняя форма SIP: rejected" in text
    assert "registered" not in _office_facts_block({"sip_last": {"code": "registered"}})


def test_registry_reports_progress_to_sink(db):
    from app.operator.tools.registry import ToolRegistry, ToolResult
    from app.services.hermes_nous.progress import progress_sink

    class Dummy:
        name = "web.research"
        description = "x"
        parameters: dict = {}

        def run(self, db, ctx, **params):
            return ToolResult(ok=True, message="ok")

    reg = ToolRegistry()
    reg.register(Dummy())
    events = []
    with progress_sink(events.append):
        reg.run(db, SimpleNamespace(), "web.research", url="https://example.com/a")
    assert events[0] == {"phase": "tool", "tool": "web.research", "preview": "example.com"}
    assert events[-1] == {"phase": "between", "tool": "web.research"}
    # No sink: silent no-op.
    reg.run(db, SimpleNamespace(), "web.research", url="https://example.com")


def test_close_agent_run_marks_completed_and_failed(db):
    from app.services.hermes_nous.bridge import _close_agent_run

    ctx = _ctx(db)
    rows = []
    for _ in range(3):
        row = AgentRun(
            id=uuid.uuid4(), tenant_id=ctx.tenant_id, hermes_run_id="run_x", status="running",
            attempt=1, checkpoint={}, usage={},
        )
        db.add(row)
        rows.append(row)
    db.commit()
    _close_agent_run(db, ctx, rows[0].id, {"status": "completed"}, polled=True, output="hi")
    _close_agent_run(db, ctx, rows[1].id, {"status": "failed"}, polled=True)
    _close_agent_run(db, ctx, rows[2].id, {"status": "running"}, polled=False)
    db.expire_all()
    assert rows[0].status == "completed" and rows[0].finished_at is not None
    assert rows[1].status == "failed"
    assert rows[2].status == "running"
    other = _ctx(db, "other")
    _close_agent_run(db, other, rows[2].id, {"status": "completed"}, polled=True)
    db.expire_all()
    assert rows[2].status == "running"


def test_line_status_does_not_claim_number_works_without_phone(db):
    ctx = _ctx(db)
    no_phone = line_status(db, ctx, phone_ok=False)
    assert "Номер уже работает" not in no_phone["message_ru"]
    assert "не подключён" in no_phone["message_ru"]
    assert no_phone["test_call_allowed"] is False
    legacy = line_status(db, ctx)
    assert "Номер уже работает" in legacy["message_ru"]


def test_connector_set_calendar_does_not_claim_connected(db, monkeypatch):
    from app.adapters.connectors.base import ConnectorResult
    from app.operator.tools.office_setup import OfficeConnectorSetTool

    ctx = _ctx(db)

    def _probe(*, tenant_slug, config):
        return ConnectorResult(
            ok=True, configured=True, kind="calendar", message="ok",
            data={"health": {"creds_policy": "tools_first", "stub_mode": True}},
        )

    from unittest.mock import MagicMock

    monkeypatch.setattr(
        "app.services.connectors.get_connector",
        lambda kind: MagicMock(kind=kind, probe=_probe, status=lambda **k: ConnectorResult(ok=True, configured=True, kind=kind)),
    )
    monkeypatch.setattr(
        "app.operator.tools.office_setup.probe_tenant_connector", lambda db, ctx, kind: {"ok": True}
    )
    out = OfficeConnectorSetTool().run(db, ctx, kind="calendar", enabled=True)
    assert out.data["usable"] is False and out.data["needs"] == "owner_account"
    assert "НЕ подключен" in out.message and "calendar_yandex" in out.message


def test_calendar_account_save_verifies_for_real(db):
    from app.services import tenant_vault

    ctx = _ctx(db)
    with patch(
        "app.services.office_accounts.verify_account",
        return_value={"ok": False, "code": "auth", "message_ru": "не подошли"},
    ):
        out = tenant_vault.save_secret(db, ctx, kind="calendar_yandex", login="ivan@yandex.ru", password="a" * 16)
    assert out["account_probe"]["ok"] is False and out.get("pending_credential_form")
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    assert "verified_at" not in tenant.settings["secrets"]["calendar_yandex"]
    with patch(
        "app.services.office_accounts.verify_account",
        return_value={"ok": True, "code": "verified", "message_ru": "ok", "events_14d": 3},
    ):
        out = tenant_vault.save_secret(db, ctx, kind="calendar_yandex", login="ivan@yandex.ru", password="a" * 16)
    db.expire_all()
    tenant = db.query(Tenant).filter(Tenant.id == ctx.tenant_id).one()
    assert tenant.settings["secrets"]["calendar_yandex"]["verified_at"]
    form = tenant_vault.credential_form_spec("calendar_mailru")
    assert form["kind"] == "calendar_mailru"
    assert "ivan@mail.ru" in form["fields"][0]["placeholder"]
    assert "Пароли для внешних приложений" in form["fields"][1]["help"]
