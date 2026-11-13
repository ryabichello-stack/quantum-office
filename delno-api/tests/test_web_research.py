"""Hermes browser research — URL extract + multi-page dossier."""

from __future__ import annotations

from unittest.mock import patch

from app.api.v1.operator import _extract_http_urls, _wants_web_research
from app.services.web_browser import extract_same_host_links, extract_urls, research_site


def test_extract_urls_from_chat():
    urls = extract_urls("посмотри https://example.com/about и ещё http://foo.ru/")
    assert "https://example.com/about" in urls
    assert "http://foo.ru/" in urls


def test_wants_web_research_url_and_verbs():
    assert _wants_web_research("https://acme.ru — расскажи что это")
    assert _wants_web_research("зайди на сайт и скажи чем занимаются")
    assert _extract_http_urls("link https://t.me/somechannel")


def test_extract_same_host_links_prefers_about():
    html = """
    <a href="/blog/1">b</a>
    <a href="/about">About</a>
    <a href="https://other.com/x">x</a>
    <a href="/contacts">Contacts</a>
    """
    links = extract_same_host_links(html, "https://acme.ru/", limit=5)
    assert any("/about" in u for u in links)
    assert all("other.com" not in u for u in links)


def test_research_site_traces_browse(monkeypatch):
    def fake_browse(url, max_chars=9000):
        return {
            "ok": True,
            "engine": "httpx",
            "url": url,
            "title": "Acme",
            "text": "Мы делаем виджеты. Контакты: sales@acme.ru " * 5,
            "chars": 200,
            "links": ["https://example.com/about"],
        }

    with (
        patch("app.services.web_browser.browse_page", side_effect=fake_browse),
        patch("app.services.web_browser.search_web", return_value={"ok": True, "items": []}),
        patch("app.services.web_browser._assert_public_url", return_value=None),
    ):
        out = research_site("https://example.com", max_pages=2, also_search=False)

    assert out["ok"]
    assert out["dossier"]
    assert any(t.get("tool") == "web.browse" for t in out["tool_trace"])
