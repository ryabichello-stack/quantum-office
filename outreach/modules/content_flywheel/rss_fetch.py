"""RSS/Atom feed fetch — universal news source for any industry (stdlib only)."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree.ElementTree import Element

logger = logging.getLogger("ava-outreach.content_flywheel.rss_fetch")

_USER_AGENT = "AVA-Flywheel/1.0 (+https://a.47z.ru)"
_STRIP_TAGS = re.compile(r"<[^>]+>")


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1].lower()
    return tag.lower()


def _text(el: Element | None) -> str:
    if el is None:
        return ""
    return (el.text or "").strip()


def _find_child(parent: Element, names: tuple[str, ...]) -> Element | None:
    for child in parent:
        if _local(child.tag) in names:
            return child
    return None


def _strip_html(raw: str) -> str:
    return re.sub(r"\s+", " ", _STRIP_TAGS.sub(" ", raw or "")).strip()


def _parse_date(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw[:25], fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        except ValueError:
            continue
    return None


def parse_feed_xml(xml_text: str, *, feed_url: str = "") -> list[dict[str, Any]]:
    """Parse RSS 2.0 or Atom feed XML into normalized news items."""
    root = ET.fromstring(xml_text)
    tag = _local(root.tag)
    items: list[dict[str, Any]] = []

    if tag == "rss":
        channel = _find_child(root, ("channel",))
        if channel is None:
            channel = root
        for entry in channel:
            if _local(entry.tag) != "item":
                continue
            items.append(_normalize_rss_item(entry, feed_url=feed_url))
    elif tag == "feed":
        for entry in root:
            if _local(entry.tag) == "entry":
                items.append(_normalize_atom_entry(entry, feed_url=feed_url))
    return [i for i in items if i.get("title")]


def _normalize_rss_item(item: Element, *, feed_url: str) -> dict[str, Any]:
    title = _text(_find_child(item, ("title",)))
    body = _text(_find_child(item, ("description", "encoded", "content")))
    if not body:
        body = _text(_find_child(item, ("summary", "content")))
    body = _strip_html(body)
    link = _text(_find_child(item, ("link",)))
    guid_el = _find_child(item, ("guid",))
    guid = _text(guid_el) or link or title
    pub = _text(_find_child(item, ("pubdate", "date", "published", "updated")))
    return {
        "title": title[:300],
        "body": body[:8000],
        "link": link[:500],
        "external_id": (guid or title)[:200],
        "published_at": _parse_date(pub),
        "image_url": _extract_image(item),
        "raw": {"mode": "rss", "feed_url": feed_url},
    }


def _normalize_atom_entry(entry: Element, *, feed_url: str) -> dict[str, Any]:
    title = _text(_find_child(entry, ("title",)))
    body = _text(_find_child(entry, ("summary", "content")))
    body = _strip_html(body)
    link = ""
    for child in entry:
        if _local(child.tag) == "link":
            rel = (child.attrib.get("rel") or "alternate").lower()
            href = (child.attrib.get("href") or "").strip()
            if href and (rel in ("alternate", "") or not link):
                link = href
    guid = _text(_find_child(entry, ("id",))) or link or title
    pub = _text(_find_child(entry, ("published", "updated",)))
    return {
        "title": title[:300],
        "body": body[:8000],
        "link": link[:500],
        "external_id": guid[:200],
        "published_at": _parse_date(pub),
        "image_url": _extract_image(entry),
        "raw": {"mode": "atom", "feed_url": feed_url},
    }


def _extract_image(parent: Element) -> str:
    for child in parent:
        if _local(child.tag) == "enclosure":
            typ = (child.attrib.get("type") or "").lower()
            url = (child.attrib.get("url") or "").strip()
            if url and typ.startswith("image/"):
                return url[:500]
        if _local(child.tag) in ("media:content", "content"):
            url = (child.attrib.get("url") or "").strip()
            if url:
                return url[:500]
    return ""


def fetch_feed_items(feed_url: str, *, limit: int = 10, timeout: float = 20.0) -> list[dict[str, Any]]:
    """Fetch and parse feed URL. Returns [] on failure (logged)."""
    url = (feed_url or "").strip()
    if not url:
        return []
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        text = data.decode("utf-8", errors="replace")
        items = parse_feed_xml(text, feed_url=url)
        return items[: max(1, min(limit, 30))]
    except (urllib.error.URLError, urllib.error.HTTPError, ET.ParseError, TimeoutError) as exc:
        logger.warning("rss fetch failed %s: %s", url, exc)
        return []
