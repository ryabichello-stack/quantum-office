"""Hermes web tools — search + fetch (+ optional Playwright browse)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from app.services.openai_http import openai_proxy_url

USER_AGENT = (
    "Mozilla/5.0 (compatible; DELNO-Hermes/1.0; +https://dlno.ru) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip += 1
        if tag == "title":
            self._in_title = True
        if tag in {"p", "br", "li", "h1", "h2", "h3", "tr", "div"}:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self._skip:
            self._skip -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        text = data.strip()
        if not text:
            return
        if self._in_title and not self.title:
            self.title = text[:200]
        self._chunks.append(text + " ")

    def text(self) -> str:
        raw = "".join(self._chunks)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _client(timeout: float = 20.0) -> httpx.Client:
    proxy = openai_proxy_url()  # same egress bridge when set
    headers = {"User-Agent": USER_AGENT, "Accept-Language": "ru,en;q=0.8"}
    if proxy:
        return httpx.Client(timeout=timeout, proxy=proxy, headers=headers, follow_redirects=True)
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True)


def html_to_text(html: str) -> tuple[str, str]:
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:  # noqa: BLE001
        pass
    return parser.title, parser.text()


def fetch_url(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "error": "invalid_url"}
    try:
        with _client() as client:
            resp = client.get(url)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "fetch_failed", "detail": str(exc)[:200]}
    content_type = (resp.headers.get("content-type") or "").lower()
    body = resp.text if "html" in content_type or "text" in content_type or not content_type else ""
    title, text = html_to_text(body) if body else ("", "")
    if not text and body:
        text = body
    text = text[:max_chars]
    return {
        "ok": resp.status_code < 400,
        "status_code": resp.status_code,
        "url": str(resp.url),
        "title": title,
        "text": text,
        "chars": len(text),
    }


def _ddg_results(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    # DuckDuckGo HTML (no API key). Works via egress proxy when configured.
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    with _client() as client:
        resp = client.post(url, data={"q": query})
        html = resp.text
    results: list[dict[str, str]] = []
    # result links look like <a rel="nofollow" class="result__a" href="...">
    for match in re.finditer(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.I | re.S,
    ):
        href = match.group(1)
        title = re.sub("<[^>]+>", "", match.group(2)).strip()
        # DDG sometimes wraps redirects
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            href = unquote(qs.get("uddg", [href])[0])
        if not href.startswith("http"):
            continue
        results.append({"title": title[:200], "url": href})
        if len(results) >= limit:
            break
    return results


def search_web(query: str, *, limit: int = 5) -> dict[str, Any]:
    q = (query or "").strip()
    if len(q) < 2:
        return {"ok": False, "error": "empty_query"}
    try:
        items = _ddg_results(q, limit=max(1, min(limit, 10)))
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "search_failed", "detail": str(exc)[:200]}
    return {"ok": True, "query": q, "items": items, "total": len(items)}


def browse_page(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    """Prefer Playwright when installed; otherwise fall back to HTTP fetch."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        out = fetch_url(url, max_chars=max_chars)
        out["engine"] = "httpx"
        return out

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "error": "invalid_url"}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.goto(url, wait_until="domcontentloaded", timeout=25000)
            html = page.content()
            final_url = page.url
            browser.close()
        title, text = html_to_text(html)
        text = text[:max_chars]
        return {
            "ok": True,
            "engine": "playwright",
            "url": final_url,
            "title": title,
            "text": text,
            "chars": len(text),
        }
    except Exception as exc:  # noqa: BLE001
        out = fetch_url(url, max_chars=max_chars)
        out["engine"] = "httpx_fallback"
        out["playwright_error"] = str(exc)[:200]
        return out
