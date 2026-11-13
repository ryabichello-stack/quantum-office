"""Hermes web tools — search + fetch (+ Playwright browse) + multi-page research."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse

import httpx

from app.services.openai_http import openai_proxy_url

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 DELNO-Hermes/1.1"
)

_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)

# Public social / messenger hosts — best-effort (often login-walled).
_SOCIAL_HOSTS = (
    "t.me",
    "telegram.me",
    "telegram.org",
    "instagram.com",
    "www.instagram.com",
    "max.ru",
    "web.max.ru",
    "vk.com",
    "www.vk.com",
    "facebook.com",
    "www.facebook.com",
    "x.com",
    "twitter.com",
    "youtube.com",
    "www.youtube.com",
    "youtu.be",
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


def _client(*, timeout: float = 25.0, use_proxy: bool = True) -> httpx.Client:
    proxy = openai_proxy_url() if use_proxy else None
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


def extract_urls(text: str) -> list[str]:
    """Pull http(s) URLs from free text (chat message)."""
    found: list[str] = []
    seen: set[str] = set()
    for match in _URL_RE.finditer(text or ""):
        raw = match.group(0).rstrip(".,;:!?")
        if raw in seen:
            continue
        seen.add(raw)
        found.append(raw)
    return found


def _assert_public_url(url: str) -> str | None:
    """Return error code if URL is not a safe public http(s) target."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "invalid_url"
    try:
        from app.services.website_import import assert_website_url_safe, normalize_website_url

        normalized = normalize_website_url(url)
        assert_website_url_safe(normalized)
        return None
    except ValueError as exc:
        return str(exc) or "url_not_allowed"
    except Exception:  # noqa: BLE001
        # Fail open only for parse/import issues — still block obviously local hosts.
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"} or host.endswith(".local"):
            return "url_not_allowed"
        return None


def is_social_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    return host in {h[4:] if h.startswith("www.") else h for h in _SOCIAL_HOSTS} or any(
        host == h or host.endswith("." + h) for h in ("t.me", "telegram.me", "instagram.com", "max.ru")
    )


def _same_host(a: str, b: str) -> bool:
    ha = (urlparse(a).hostname or "").lower().removeprefix("www.")
    hb = (urlparse(b).hostname or "").lower().removeprefix("www.")
    return bool(ha) and ha == hb


def extract_same_host_links(html: str, base_url: str, *, limit: int = 12) -> list[str]:
    """Collect promising same-host paths (about/contacts/services/…)."""
    prefer = (
        "about",
        "o-nas",
        "onas",
        "company",
        "kontakt",
        "contact",
        "uslugi",
        "service",
        "product",
        "price",
        "ceny",
        "team",
        "blog",
        "news",
        "faq",
        "privac",
        "offer",
        "tarif",
    )
    scored: list[tuple[int, str]] = []
    seen: set[str] = set()
    for href in _HREF_RE.findall(html or ""):
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in {"http", "https"}:
            continue
        if not _same_host(base_url, full):
            continue
        clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path or '/'}"
        if clean.rstrip("/") == urlparse(base_url).path and parsed.netloc == urlparse(base_url).netloc:
            # skip exact home duplicates later via seen
            pass
        key = clean.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        path_l = (parsed.path or "/").lower()
        score = 0
        for i, token in enumerate(prefer):
            if token in path_l:
                score = 100 - i
                break
        if path_l in {"/", ""}:
            score = -1
        if score >= 0:
            scored.append((score, clean))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [u for _, u in scored[:limit]]


def fetch_url(url: str, *, max_chars: int = 12000) -> dict[str, Any]:
    blocked = _assert_public_url(url)
    if blocked:
        return {"ok": False, "error": blocked, "url": url}
    last_err = ""
    for use_proxy in (True, False):
        try:
            with _client(use_proxy=use_proxy) as client:
                resp = client.get(url)
            content_type = (resp.headers.get("content-type") or "").lower()
            body = resp.text if "html" in content_type or "text" in content_type or not content_type else ""
            title, text = html_to_text(body) if body else ("", "")
            if not text and body:
                text = body
            text = text[:max_chars]
            links = extract_same_host_links(body, str(resp.url), limit=12) if body else []
            return {
                "ok": resp.status_code < 400 and bool(text),
                "status_code": resp.status_code,
                "url": str(resp.url),
                "title": title,
                "text": text,
                "chars": len(text),
                "links": links,
                "html_chars": len(body or ""),
                "via_proxy": use_proxy and bool(openai_proxy_url()),
                "social": is_social_url(str(resp.url)),
            }
        except Exception as exc:  # noqa: BLE001
            last_err = str(exc)[:200]
            continue
    return {"ok": False, "error": "fetch_failed", "detail": last_err, "url": url}


def _parse_ddg_html(html: str, *, limit: int) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    # Classic SERP: <a rel="nofollow" class="result__a" href="...">
    patterns = (
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        r'href="([^"]+)"[^>]*class="result__a"[^>]*>(.*?)</a>',
    )
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, html, flags=re.I | re.S):
            href = match.group(1)
            title = re.sub("<[^>]+>", "", match.group(2)).strip()
            if "uddg=" in href:
                qs = parse_qs(urlparse(href).query)
                href = unquote(qs.get("uddg", [href])[0])
            if not href.startswith("http"):
                continue
            if href in seen:
                continue
            seen.add(href)
            results.append({"title": title[:200] or href, "url": href})
            if len(results) >= limit:
                return results
    return results


def _ddg_results(query: str, *, limit: int = 5) -> list[dict[str, str]]:
    """DuckDuckGo HTML (no API key). Retry proxy→direct; POST then GET."""
    last_err: Exception | None = None
    for use_proxy in (True, False):
        try:
            with _client(use_proxy=use_proxy) as client:
                resp = client.post("https://html.duckduckgo.com/html/", data={"q": query})
                items = _parse_ddg_html(resp.text, limit=limit)
                if items:
                    return items
                # Some edges return challenge/empty — try GET with q=
                resp = client.get(
                    f"https://html.duckduckgo.com/html/?q={quote_plus(query)}",
                )
                items = _parse_ddg_html(resp.text, limit=limit)
                if items:
                    return items
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    if last_err:
        raise last_err
    return []


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
    blocked = _assert_public_url(url)
    if blocked:
        return {"ok": False, "error": blocked, "url": url}

    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        out = fetch_url(url, max_chars=max_chars)
        out["engine"] = out.get("engine") or "httpx"
        return out

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=USER_AGENT)
            page.set_extra_http_headers({"Accept-Language": "ru,en;q=0.8"})
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_timeout(800)
            except Exception:  # noqa: BLE001
                pass
            html = page.content()
            final_url = page.url
            browser.close()
        title, text = html_to_text(html)
        text = text[:max_chars]
        links = extract_same_host_links(html, final_url, limit=12)
        return {
            "ok": bool(text) or bool(title),
            "engine": "playwright",
            "url": final_url,
            "title": title,
            "text": text,
            "chars": len(text),
            "links": links,
            "social": is_social_url(final_url),
        }
    except Exception as exc:  # noqa: BLE001
        out = fetch_url(url, max_chars=max_chars)
        out["engine"] = "httpx_fallback"
        out["playwright_error"] = str(exc)[:200]
        return out


def research_site(
    url: str,
    *,
    max_pages: int = 5,
    max_chars_per_page: int = 9000,
    also_search: bool = True,
    extra_paths: tuple[str, ...] | list[str] | None = None,
) -> dict[str, Any]:
    """
    Open a URL in Hermes browser, crawl key same-host pages, optionally
    supplement with a web search. Returns a dossier for the LLM to answer from.
    """
    seed = (url or "").strip()
    if not seed.startswith(("http://", "https://")):
        seed = f"https://{seed}"
    blocked = _assert_public_url(seed)
    if blocked:
        out: dict[str, Any] = {"ok": False, "error": blocked, "url": seed}
        if blocked == "url_unreachable":
            try:
                from app.services.website_import import suggest_reachable_host

                host = (urlparse(seed).hostname or "").lower()
                suggestion = suggest_reachable_host(host)
                if suggestion:
                    out["suggestion"] = suggestion
                    out["suggestion_url"] = f"https://{suggestion}/"
                    out["detail"] = (
                        f"Домен «{host}» не резолвится. Похоже на опечатку — "
                        f"имели в виду https://{suggestion}/ ?"
                    )
            except Exception:  # noqa: BLE001
                pass
        return out

    pages: list[dict[str, Any]] = []
    tool_trace: list[dict[str, Any]] = []
    primary = browse_page(seed, max_chars=max_chars_per_page)
    tool_trace.append(
        {
            "tool": "web.browse",
            "ok": bool(primary.get("ok")),
            "url": primary.get("url") or seed,
            "title": primary.get("title") or "",
            "engine": primary.get("engine") or "",
            "chars": primary.get("chars") or 0,
        }
    )
    if primary.get("ok"):
        pages.append(primary)
    elif primary.get("text"):
        pages.append(primary)

    candidates = list(primary.get("links") or [])
    # Always try common paths even if HTML had few links.
    base = primary.get("url") or seed
    parsed = urlparse(base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    default_paths = (
        "/about",
        "/o-nas",
        "/contacts",
        "/kontakt",
        "/uslugi",
        "/services",
        "/pricing",
        "/price",
        "/faq",
        "/blog",
        "/news",
    )
    for path in tuple(extra_paths or ()) + default_paths:
        if not path:
            continue
        if not str(path).startswith("/"):
            path = "/" + str(path)
        candidates.append(origin + str(path))

    seen = {(primary.get("url") or seed).rstrip("/").lower()}
    for link in candidates:
        if len(pages) >= max_pages:
            break
        key = link.rstrip("/").lower()
        if key in seen:
            continue
        seen.add(key)
        page = browse_page(link, max_chars=max_chars_per_page)
        tool_trace.append(
            {
                "tool": "web.browse",
                "ok": bool(page.get("ok")),
                "url": page.get("url") or link,
                "title": page.get("title") or "",
                "engine": page.get("engine") or "",
                "chars": page.get("chars") or 0,
            }
        )
        if page.get("ok") and (page.get("chars") or 0) >= 80:
            pages.append(page)

    search_items: list[dict[str, str]] = []
    host = (urlparse(seed).hostname or "").removeprefix("www.")
    if also_search and host and not is_social_url(seed):
        q = f"{host} компания услуги контакты"
        searched = search_web(q, limit=5)
        tool_trace.append(
            {
                "tool": "web.search",
                "ok": bool(searched.get("ok")),
                "query": q,
                "count": len(searched.get("items") or []),
            }
        )
        if searched.get("ok"):
            search_items = list(searched.get("items") or [])
            for item in search_items[:2]:
                if len(pages) >= max_pages + 2:
                    break
                u = str(item.get("url") or "")
                if not u or u.rstrip("/").lower() in seen:
                    continue
                if not _same_host(seed, u) and host not in u:
                    # still allow off-host SERP hits for context (reviews etc.)
                    pass
                seen.add(u.rstrip("/").lower())
                page = fetch_url(u, max_chars=max_chars_per_page // 2)
                page["engine"] = page.get("engine") or "httpx"
                tool_trace.append(
                    {
                        "tool": "web.fetch",
                        "ok": bool(page.get("ok")),
                        "url": page.get("url") or u,
                        "title": page.get("title") or item.get("title") or "",
                        "engine": page.get("engine") or "",
                        "chars": page.get("chars") or 0,
                    }
                )
                if page.get("ok") and (page.get("chars") or 0) >= 80:
                    pages.append(page)

    dossier_parts: list[str] = []
    for i, page in enumerate(pages, 1):
        dossier_parts.append(
            f"### Страница {i}: {page.get('title') or page.get('url')}\n"
            f"URL: {page.get('url')}\n"
            f"{(page.get('text') or '')[:max_chars_per_page]}"
        )
    dossier = "\n\n".join(dossier_parts).strip()
    social = is_social_url(seed)
    note = ""
    if social and (not pages or sum(int(p.get("chars") or 0) for p in pages) < 200):
        note = (
            "Соцсеть/мессенджер часто закрывает контент без логина. "
            "Ниже — то, что удалось снять публично; остальное нужно уточнить у владельца."
        )

    return {
        "ok": bool(pages),
        "url": seed,
        "pages": [
            {
                "url": p.get("url"),
                "title": p.get("title"),
                "chars": p.get("chars"),
                "engine": p.get("engine"),
            }
            for p in pages
        ],
        "dossier": dossier[:45000],
        "search_items": search_items,
        "tool_trace": tool_trace,
        "social": social,
        "note": note,
        "error": None if pages else (primary.get("error") or "browse_empty"),
        "detail": primary.get("detail") or primary.get("playwright_error"),
    }
