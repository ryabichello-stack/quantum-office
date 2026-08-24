"""Telegram public channel parser — t.me/s preview (no extra deps).

Works for public channels (@name, t.me/name). Private channels require
bot admin + separate incremental collector (future).
"""

from __future__ import annotations

import html as html_lib
import logging
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ava-outreach.content_flywheel.tg_fetch")

_USER_AGENT = "Mozilla/5.0 (compatible; AVA-Flywheel/1.0; +https://a.47z.ru)"
_MSG_WRAP = "tgme_widget_message_wrap"
_STRIP_TAGS = re.compile(r"<[^>]+>")


def tg_item_limit() -> int:
    try:
        return max(1, min(20, int(os.getenv("FLYWHEEL_TG_LIMIT") or "8")))
    except ValueError:
        return 8


def normalize_channel_handle(handle: str) -> str:
    """@channel, t.me/channel, https://t.me/s/channel → channel."""
    raw = (handle or "").strip()
    if not raw:
        return ""
    raw = raw.split("?")[0].rstrip("/")
    for prefix in (
        "https://t.me/s/",
        "http://t.me/s/",
        "https://t.me/",
        "http://t.me/",
        "t.me/s/",
        "t.me/",
    ):
        if raw.lower().startswith(prefix):
            raw = raw[len(prefix) :]
            break
    if raw.startswith("@"):
        raw = raw[1:]
    return re.sub(r"[^a-zA-Z0-9_]", "", raw.split("/")[0])


def _preview_url(channel: str) -> str:
    return f"https://t.me/s/{channel}"


def _message_id(post_key: str) -> int:
    try:
        return int((post_key or "").rsplit("/", 1)[-1])
    except ValueError:
        return 0


def parse_channel_html(html_text: str, *, channel: str) -> list[dict[str, Any]]:
    """Parse Telegram public preview HTML into normalized post dicts."""
    channel = normalize_channel_handle(channel)
    if not channel:
        return []

    chunks = html_text.split(_MSG_WRAP)
    messages: list[dict[str, Any]] = []

    for chunk in chunks[1:]:
        post_m = re.search(r'data-post="([^"]+)"', chunk)
        if not post_m:
            continue
        post_key = post_m.group(1)
        msg_id = _message_id(post_key)
        if not msg_id:
            continue

        time_m = re.search(r'<time datetime="([^"]+)"', chunk)
        published_at = _parse_iso(time_m.group(1) if time_m else "")

        text = ""
        text_m = re.search(
            r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>\s*</div>',
            chunk,
            re.S,
        )
        if not text_m:
            text_m = re.search(r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', chunk, re.S)
        if text_m:
            text = _STRIP_TAGS.sub(" ", text_m.group(1))
            text = html_lib.unescape(re.sub(r"\s+", " ", text).strip())

        if not text:
            # Photo/video-only posts may have no text block
            fwd_m = re.search(r'class="tgme_widget_message_forwarded_from_name"[^>]*>([^<]+)', chunk)
            if fwd_m:
                text = html_lib.unescape(fwd_m.group(1).strip())
            if not text:
                continue

        image_url = ""
        photo_m = re.search(r"background-image:url\('([^']+)'\)", chunk)
        if photo_m:
            image_url = photo_m.group(1).strip()
            if image_url.startswith("//"):
                image_url = "https:" + image_url

        title = text.split("\n", 1)[0][:200]
        if len(title) < 12 and len(text) > len(title):
            title = text[:120]

        messages.append(
            {
                "channel": channel,
                "external_id": post_key,
                "message_id": msg_id,
                "title": title[:300],
                "body": text[:8000],
                "link": f"https://t.me/{channel}/{msg_id}",
                "image_url": image_url[:500],
                "published_at": published_at,
                "raw": {"mode": "tg_public", "post": post_key, "channel": channel},
            }
        )

    messages.sort(key=lambda m: int(m.get("message_id") or 0), reverse=True)
    return messages


def _parse_iso(raw: str) -> str | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    except ValueError:
        return None


def fetch_channel_posts(handle: str, *, limit: int | None = None) -> list[dict[str, Any]]:
    """Fetch recent posts from a public Telegram channel."""
    channel = normalize_channel_handle(handle)
    if not channel:
        return []
    lim = limit if limit is not None else tg_item_limit()
    url = _preview_url(channel)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.warning("tg fetch failed %s: %s", channel, exc)
        return []

    items = parse_channel_html(html_text, channel=channel)
    if not items:
        logger.info("tg fetch empty channel=%s (private or no public preview?)", channel)
    return items[: max(1, min(lim, 20))]
