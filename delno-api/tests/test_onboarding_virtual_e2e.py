"""Full virtual onboarding walkthrough (owner perspective).

Mocks knowledge upload + SIP probe + site browse. Asserts the path:
KB draft → confirm → phone next → DID → SIP form on «делай» → SIP save.
Also checks site / social / text routing.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.operator import _credential_form_kind_from_message, _wants_kb_agent_work
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import ToolResult, registry
from app.services import hermes_ops, phone_provision
from app.services.hermes_kb_build import build_company_kb_draft
from app.services.hermes_nous.onboarding import confirm_kb_draft
from app.services.tenant_vault import credential_form_spec, save_secret


def test_virtual_onboarding_path_kb_to_sip():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="virt-e2e",
        name="E2E Co",
        settings={
            "locale": "ru",
            "hermes": {},
            "hermes_nous": {"office_loop": {"phase": "welcome"}},
            "connectors": {},
        },
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    register_builtin_tools()

    st0 = hermes_ops.office_setup_status(db, ctx)
    assert (st0.get("next_steps") or [{}])[0].get("id") == "kb"

    dossier = "E2E Co выплаты. Комиссия 0.4%. office@e2e.ru https://t.me/e2e"

    def fake_research(url, **_kw):
        return {
            "ok": True,
            "url": url,
            "pages": [{"url": url, "title": "E2E", "chars": 100, "engine": "httpx"}],
            "dossier": f"URL:{url}\n{dossier}",
            "search_items": [],
            "tool_trace": [],
            "social": False,
            "note": "",
        }

    with (
        patch("app.services.hermes_kb_build.web_browser.research_site", side_effect=fake_research),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value=st0,
        ),
    ):
        draft = build_company_kb_draft(
            db, ctx, urls=["https://e2e.example"], also_search=False
        )
    assert draft.get("ok") and draft.get("kb_draft")

    orig_run = registry.run

    def run_wrap(db_, ctx_, name, **params):
        if name == "upload_knowledge_snippet":
            return ToolResult(ok=True, data={"document_id": "doc-e2e"}, message="uploaded")
        return orig_run(db_, ctx_, name, **params)

    registry.run = run_wrap  # type: ignore
    try:
        conf = confirm_kb_draft(db, ctx)
    finally:
        registry.run = orig_run
    assert conf.get("ok"), conf

    st1 = hermes_ops.office_setup_status(db, ctx)
    assert (st1.get("checks") or {}).get("kb", {}).get("ok") is True
    assert (st1.get("next_steps") or [{}])[0].get("id") == "phone"

    prov = phone_provision.provision_phone(db, ctx, e164="+79699665899")
    assert prov.get("ok")

    kind = _credential_form_kind_from_message(
        "делай", setup_next_id="phone", setup_substep="need_sip"
    )
    assert kind == "mango_sip"
    form = credential_form_spec("mango_sip")
    assert form.get("kind") == "mango_sip"

    with patch(
        "app.services.sip_probe.after_vault_sip_save",
        return_value={"ok": True, "message_ru": "Registered", "skipped": False},
    ):
        saved = save_secret(
            db, ctx, kind="mango_sip", login="79991234567/1", password="secret-pass-ok"
        )
    assert saved.get("ok") or saved.get("configured"), saved

    st2 = hermes_ops.office_setup_status(db, ctx)
    phone = (st2.get("checks") or {}).get("phone") or {}
    detail = phone.get("detail") or {}
    assert int(detail.get("active_dids") or 0) >= 1
    assert detail.get("sip_configured") is True

    assert _wants_kb_agent_work("https://t.me/acme")
    assert _wants_kb_agent_work(
        "Мы делаем выплаты бизнесу от 5 млн, комиссия от 0.4%, ICP ломбарды"
    )
    db.close()
