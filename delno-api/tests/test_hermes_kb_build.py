"""Deep multi-source KB build for Hermes onboarding."""

from __future__ import annotations

import uuid
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.db import Base
from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.models.user import User  # noqa: F401
from app.operator.setup_intent import parse_setup_intent
from app.operator.tools import register_builtin_tools
from app.operator.tools.registry import registry
from app.services.hermes_kb_build import (
    build_company_kb_draft,
    extract_social_urls,
)


def test_extract_social_urls_kinds():
    text = (
        "Мы в https://t.me/acme_channel и https://instagram.com/acme.brand "
        "плюс https://vk.com/acme_group"
    )
    found = extract_social_urls(text)
    assert "telegram" in found
    assert "instagram" in found
    assert "vk" in found
    assert found["telegram"][0].startswith("https://t.me/")


def test_setup_intent_routes_to_build_kb_draft():
    intent = parse_setup_intent("зайди на quantumpayouts.ru и собери знания оттуда")
    assert intent is not None
    assert intent["tool"] == "office.build_kb_draft"
    assert "quantumpayouts.ru" in intent["params"]["message"]


def test_build_kb_draft_tool_registered():
    register_builtin_tools()
    assert registry.get("office.build_kb_draft") is not None


def test_build_company_kb_draft_saves_draft_and_asks(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(
        id=uuid.uuid4(),
        slug="kb-build",
        name="Acme Widgets",
        settings={},
        is_active=True,
    )
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
            "next_steps": [{"id": "kb", "title": "О компании", "hint": "сайт"}],
        },
    )

    dossier = (
        "Мы делаем виджеты для B2B. Контакты: sales@acme.ru. "
        "Канал https://t.me/acme_news прайс по запросу."
    )

    def fake_research(url, max_pages=5, also_search=True, extra_paths=None, **_kw):
        return {
            "ok": True,
            "url": url,
            "pages": [
                {"url": url, "title": "Acme", "chars": len(dossier), "engine": "httpx"},
                {"url": url.rstrip("/") + "/about", "title": "О нас", "chars": 200, "engine": "httpx"},
            ],
            "dossier": f"### Страница 1\nURL: {url}\n{dossier}",
            "search_items": [],
            "tool_trace": [{"tool": "web.browse", "ok": True, "url": url}],
            "social": False,
            "note": "",
        }

    with (
        patch("app.services.hermes_kb_build.web_browser.research_site", side_effect=fake_research),
        patch(
            "app.services.hermes_kb_build.web_browser.search_web",
            return_value={
                "ok": True,
                "items": [
                    {
                        "title": "Acme отзывы",
                        "url": "https://news.example/acme",
                        "snippet": "хорошие виджеты",
                    }
                ],
            },
        ),
        patch(
            "app.services.hermes_kb_build.web_browser.fetch_url",
            return_value={
                "ok": True,
                "url": "https://news.example/acme",
                "title": "Обзор",
                "text": "Acme — лидер виджетов. " * 10,
                "chars": 200,
                "engine": "httpx",
            },
        ),
        patch(
            "app.services.hermes_kb_build._synthesize_markdown",
            return_value={
                "title": "Acme Widgets — профиль (черновик)",
                "body": "# Профиль\n\n## Кто мы\nДелаем виджеты\n\n## Контакты\nsales@acme.ru\n" * 3,
            },
        ),
    ):
        out = build_company_kb_draft(
            db,
            ctx,
            urls=["https://acme.example"],
            max_pages=6,
            also_search=True,
        )

    assert out["ok"] is True
    assert out["kb_draft"]
    assert out["kb_draft"]["status"] == "draft"
    assert out["social_found"].get("telegram")
    assert out["questions"]
    assert "черновик" in (out["message"] or "").lower()
    db.refresh(tenant)
    nous = (tenant.settings or {}).get("hermes_nous") or {}
    loop = nous.get("office_loop") or {}
    assert (loop.get("kb_draft") or {}).get("status") == "draft"
    # Must not auto-mark kb_ready
    hermes = (tenant.settings or {}).get("hermes") or {}
    assert hermes.get("kb_ready") is not True
    db.close()
