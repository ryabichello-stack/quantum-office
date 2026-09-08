"""P4 — website import and instant demo."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.core.tenant import TenantContext
from app.models.tenant import Tenant
from app.services.instant_demo import import_website_to_tenant, preview_website
from app.services.website_import import (
    build_knowledge_markdown,
    extract_website_content,
    normalize_website_url,
)

SAMPLE_HTML = """
<html>
<head>
  <title>Acme Corp — услуги</title>
  <meta name="description" content="Доставка и логистика по России">
</head>
<body>
  <h1>Acme Corp</h1>
  <p>Мы занимаемся доставкой по всей России уже 10 лет.</p>
  <h2>Контакты</h2>
  <p>Телефон +7 999 000-00-00, email hello@acme.test</p>
</body>
</html>
"""


def test_normalize_website_url_adds_https():
    assert normalize_website_url("example.com") == "https://example.com/"


def test_extract_website_content_parses_html():
    data = extract_website_content(SAMPLE_HTML, url="https://example.com/")
    assert data["title"] == "Acme Corp — услуги"
    assert "Доставка" in data["description"]
    assert any("доставкой" in p.lower() for p in data["paragraphs"])


def test_build_knowledge_markdown_includes_sections():
    extracted = extract_website_content(SAMPLE_HTML, url="https://example.com/")
    md = build_knowledge_markdown(extracted)
    assert "Acme Corp" in md
    assert "example.com" in md


def test_preview_website():
    with patch("app.services.instant_demo.fetch_website_content") as mock_fetch:
        mock_fetch.return_value = {
            "url": "https://example.com/",
            "title": "Acme",
            "description": "Desc",
            "paragraphs": ["Hello world from acme website page"],
            "sections": [],
            "markdown": "# Acme\n\nHello world from acme website page",
        }
        result = preview_website("example.com")
    assert result["ok"] is True
    assert result["title"] == "Acme"
    assert len(result["sample_questions"]) == 3


def test_import_website_to_tenant():
    tenant_id = uuid.uuid4()
    tenant = Tenant(id=tenant_id, slug="acme", name="Acme", public_key="pk_test", settings={})
    ctx = TenantContext(tenant_id=tenant_id, tenant_slug="acme", role="tenant_owner")
    db = MagicMock()
    db.query.return_value.filter.return_value.one.return_value = tenant

    with patch("app.services.instant_demo.fetch_website_content") as mock_fetch:
        mock_fetch.return_value = {
            "url": "https://example.com/",
            "title": "Acme Site",
            "description": "",
            "paragraphs": ["Мы продаём качественные товары оптом и в розницу."],
            "sections": [{"heading": "О нас", "level": "h2"}],
            "markdown": "# Acme Site\n\nМы продаём качественные товары оптом и в розницу.",
        }
        with patch("app.services.instant_demo.emit_event"):
            with patch(
                "app.services.instant_demo.upsert_tenant_knowledge_document",
                return_value={"ok": True, "document_id": "doc-acme-website"},
            ):
                result = import_website_to_tenant(db, ctx, website_url="https://example.com")

    assert result["ok"] is True
    assert result["site_key"] == "pk_test"
    assert "embed.js" in result["widget_embed"]
    assert tenant.settings["instant_demo"]["url"] == "https://example.com/"


def test_normalize_website_url_rejects_empty():
    with pytest.raises(ValueError, match="url_required"):
        normalize_website_url("  ")
