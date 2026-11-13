"""Virtual onboarding walkthrough: site / social / text / mixed inputs.

Simulates how an owner would act and asserts Hermes routes + KB draft
accepts each input mode without extra «social setup».
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.operator import _looks_like_company_blurb, _wants_kb_agent_work
from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.setup_intent import parse_setup_intent
from app.services.hermes_kb_build import build_company_kb_draft
from app.services.web_browser import is_social_url


def test_input_modes_route_to_kb_agent():
    # Site / domain
    assert _wants_kb_agent_work("quantumpayouts.ru")
    assert _wants_kb_agent_work("https://quantumpayouts.ru")
    # Social-only
    assert _wants_kb_agent_work("https://t.me/quantumpayouts")
    assert _wants_kb_agent_work("https://instagram.com/quantumpayouts")
    assert _wants_kb_agent_work("https://vk.com/quantumpayouts")
    # Free-text company blurb (no URL, no «собери базу»)
    blurb = (
        "Мы делаем выплаты бизнесу от 5 млн, комиссия от 0.4%, "
        "ICP — ломбарды и МФО, продукт — СБП и карты"
    )
    assert _looks_like_company_blurb(blurb)
    assert _wants_kb_agent_work(blurb)
    # Mixed
    assert _wants_kb_agent_work(
        "Вот наш канал https://t.me/acme и сайт acme.ru — собери знания"
    )
    # Affirmations are not blurbs
    assert not _looks_like_company_blurb("да")
    assert not _wants_kb_agent_work("подтверждаю")


def test_social_hosts_recognized():
    assert is_social_url("https://t.me/acme")
    assert is_social_url("https://instagram.com/acme")
    assert is_social_url("https://vk.com/acme")
    assert is_social_url("https://max.ru/acme")
    assert not is_social_url("https://quantumpayouts.ru")


def test_setup_intent_mixed_site_and_social():
    intent = parse_setup_intent(
        "Вот наш канал https://t.me/acme и сайт acme.ru — собери знания"
    )
    assert intent is not None
    assert intent["tool"] == "office.build_kb_draft"


def _tenant_ctx():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="scenario-kb",
        name="Scenario Co",
        settings={},
        is_active=True,
    )
    db.add(tenant)
    db.commit()
    ctx = TenantContext(tenant_id=tenant.id, tenant_slug=tenant.slug, role="tenant_owner")
    return db, ctx, tenant


def _fake_research(url, max_pages=5, also_search=True, extra_paths=None, **_kw):
    social = is_social_url(url)
    text = (
        "Публичный канал Acme: новости и оферты. Контакт sales@acme.ru"
        if social
        else "Acme — B2B виджеты. Прайс по запросу. https://t.me/acme_news"
    )
    return {
        "ok": True,
        "url": url,
        "pages": [{"url": url, "title": "Acme", "chars": len(text), "engine": "httpx"}],
        "dossier": f"### Страница\nURL: {url}\n{text}",
        "search_items": [],
        "tool_trace": [{"tool": "web.browse", "ok": True, "url": url}],
        "social": social,
        "note": "login-wall possible" if social else "",
    }


def test_scenario_a_website_builds_draft():
    db, ctx, tenant = _tenant_ctx()
    with (
        patch("app.services.hermes_kb_build.web_browser.research_site", side_effect=_fake_research),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = build_company_kb_draft(db, ctx, urls=["https://acme.example"], also_search=False)
    assert out["ok"]
    assert out["kb_draft"]["status"] == "draft"
    assert out["social_found"].get("telegram")
    db.close()


def test_scenario_b_social_only_builds_draft():
    db, ctx, tenant = _tenant_ctx()
    with (
        patch("app.services.hermes_kb_build.web_browser.research_site", side_effect=_fake_research),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = build_company_kb_draft(
            db, ctx, urls=["https://t.me/acme_channel"], also_search=False, research_social=False
        )
    assert out["ok"]
    assert out["kb_draft"]["status"] == "draft"
    assert out["pages_count"] >= 1
    db.close()


def test_scenario_c_text_only_builds_draft():
    db, ctx, tenant = _tenant_ctx()
    with (
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = build_company_kb_draft(
            db,
            ctx,
            message=(
                "Мы — Scenario Co. Делаем B2B виджеты для ломбардов. "
                "Комиссия от 0.4%. Клиенты — МФО и скупка. Контакт sales@acme.ru"
            ),
            also_search=False,
        )
    assert out["ok"], out
    assert out["kb_draft"]["status"] == "draft"
    body = out["kb_draft"]["body"]
    assert "виджет" in body.lower() or "ломбард" in body.lower() or "0.4" in body
    db.close()


def test_scenario_d_mixed_url_and_text():
    db, ctx, tenant = _tenant_ctx()
    with (
        patch("app.services.hermes_kb_build.web_browser.research_site", side_effect=_fake_research),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={"ok": True, "items": []},
        ),
        patch(
            "app.services.hermes_nous.onboarding.hermes_ops.office_setup_status",
            return_value={
                "setup_complete": False,
                "message_ru": "next",
                "progress": {},
                "checks": {"kb": {"ok": False}},
                "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
            },
        ),
    ):
        out = build_company_kb_draft(
            db,
            ctx,
            message=(
                "Сайт https://acme.example канал https://t.me/acme_news — "
                "мы делаем выплаты бизнесу, комиссия от 0.5% для крупных объёмов"
            ),
            also_search=False,
        )
    assert out["ok"]
    assert out["kb_draft"]["status"] == "draft"
    # Residual prose must land in draft (not only URLs).
    assert "0.5" in out["kb_draft"]["body"] or "выплат" in out["kb_draft"]["body"].lower()
    db.close()
