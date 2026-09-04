"""P4 — Website-to-Agent: fetch public pages and build KB documents."""

from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

import httpx

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_META_DESC_RE = re.compile(
    r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
    re.I | re.S,
)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture_tag: str | None = None
        self._buffer: list[str] = []
        self.headings: list[tuple[str, str]] = []
        self.paragraphs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("h1", "h2", "h3", "p"):
            self._capture_tag = tag
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        if tag != self._capture_tag:
            return
        text = _WS_RE.sub(" ", "".join(self._buffer)).strip()
        if not text:
            self._capture_tag = None
            return
        if tag in ("h1", "h2", "h3"):
            self.headings.append((tag, text))
        elif tag == "p" and len(text) >= 24:
            self.paragraphs.append(text)
        self._capture_tag = None

    def handle_data(self, data: str) -> None:
        if self._capture_tag:
            self._buffer.append(data)


def normalize_website_url(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError("url_required")
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("invalid_scheme")
    if not parsed.netloc:
        raise ValueError("invalid_url")
    path = parsed.path or "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _hostname_blocked(hostname: str) -> bool:
    host = hostname.lower().strip(".")
    if host in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
        return True
    if host.endswith(".local") or host.endswith(".internal"):
        return True
    return False


def _ip_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
    )


def assert_website_url_safe(url: str) -> None:
    parsed = urlparse(url)
    host = parsed.hostname
    if not host or _hostname_blocked(host):
        raise ValueError("url_not_allowed")

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise ValueError("url_unreachable") from exc

    for info in infos:
        ip = info[4][0]
        if _ip_blocked(ip):
            raise ValueError("url_not_allowed")


def _strip_html(html: str) -> str:
    cleaned = _SCRIPT_STYLE_RE.sub(" ", html)
    cleaned = _TAG_RE.sub(" ", cleaned)
    return _WS_RE.sub(" ", cleaned).strip()


def extract_website_content(html: str, *, url: str) -> dict[str, Any]:
    title_match = _TITLE_RE.search(html)
    title = _WS_RE.sub(" ", title_match.group(1)).strip() if title_match else ""
    desc_match = _META_DESC_RE.search(html)
    description = _WS_RE.sub(" ", desc_match.group(1)).strip() if desc_match else ""

    parser = _HeadingParser()
    try:
        parser.feed(html)
    except Exception:
        parser = _HeadingParser()

    sections: list[dict[str, str]] = []
    for tag, heading in parser.headings[:12]:
        sections.append({"heading": heading, "level": tag})
    paragraphs = parser.paragraphs[:20]
    if not paragraphs:
        plain = _strip_html(html)
        if plain:
            paragraphs = [plain[i : i + 400] for i in range(0, min(len(plain), 2400), 400)]

    return {
        "url": url,
        "title": title or urlparse(url).netloc,
        "description": description,
        "sections": sections,
        "paragraphs": paragraphs,
    }


def build_knowledge_markdown(extracted: dict[str, Any]) -> str:
    lines = [
        f"# {extracted.get('title') or 'Сайт компании'}",
        "",
        f"Источник: {extracted.get('url')}",
        "",
    ]
    if extracted.get("description"):
        lines.extend([str(extracted["description"]), ""])

    for section in extracted.get("sections") or []:
        heading = section.get("heading")
        if heading:
            lines.extend([f"## {heading}", ""])

    lines.append("## Текст со страницы")
    lines.append("")
    for paragraph in extracted.get("paragraphs") or []:
        lines.append(str(paragraph))
        lines.append("")

    body = "\n".join(lines).strip()
    return body if len(body) >= 40 else body + "\n\n(Мало текста на странице — дополните базу знаний вручную.)"


def fetch_website_content(url: str) -> dict[str, Any]:
    normalized = normalize_website_url(url)
    assert_website_url_safe(normalized)

    headers = {
        "User-Agent": "DELNO-InstantDemo/1.0 (+https://dlno.ru)",
        "Accept": "text/html,application/xhtml+xml",
    }
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, max_redirects=3) as client:
            response = client.get(normalized, headers=headers)
    except httpx.HTTPError as exc:
        raise ValueError("fetch_failed") from exc

    if response.status_code >= 400:
        raise ValueError("fetch_failed")

    content_type = (response.headers.get("content-type") or "").lower()
    if "html" not in content_type and "text/" not in content_type:
        raise ValueError("not_html")

    html = response.text[:1_000_000]
    extracted = extract_website_content(html, url=normalized)
    extracted["markdown"] = build_knowledge_markdown(extracted)
    return extracted
