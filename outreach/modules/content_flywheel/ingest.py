"""News ingest — poll watch sources (RSS/TG/VK) + manual import."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from modules.content_flywheel.rss_fetch import fetch_feed_items
from modules.content_flywheel.tg_fetch import fetch_channel_posts, tg_item_limit


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def flywheel_enabled() -> bool:
    return (os.getenv("FLYWHEEL_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def rss_item_limit() -> int:
    try:
        return max(1, min(20, int(os.getenv("FLYWHEEL_RSS_LIMIT") or "5")))
    except ValueError:
        return 5


def default_source_handles() -> dict[str, list[str]]:
    return {
        "telegram": _split_csv(os.getenv("FLYWHEEL_SOURCE_TG") or os.getenv("OWNED_TG_CHANNELS") or ""),
        "vk": _split_csv(os.getenv("FLYWHEEL_SOURCE_VK") or os.getenv("OWNED_VK_GROUPS") or ""),
        "rss": _split_csv(os.getenv("FLYWHEEL_SOURCE_RSS") or ""),
    }


def poll_watch_sources(*, handles: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Poll configured sources. RSS + TG public channels use real fetch; VK remains stub."""
    if not flywheel_enabled():
        return []
    handles = handles or default_source_handles()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    items: list[dict[str, Any]] = []

    for feed_url in handles.get("rss") or []:
        for row in fetch_feed_items(feed_url, limit=rss_item_limit()):
            items.append(
                {
                    "platform": "rss",
                    "handle": feed_url,
                    "external_id": row.get("external_id") or "",
                    "title": row.get("title") or "",
                    "body": row.get("body") or "",
                    "image_url": row.get("image_url") or "",
                    "link": row.get("link") or "",
                    "published_at": row.get("published_at") or now,
                    "raw": row.get("raw") or {"mode": "rss", "feed_url": feed_url},
                }
            )

    for handle in handles.get("telegram") or []:
        for row in fetch_channel_posts(handle, limit=tg_item_limit()):
            items.append(
                {
                    "platform": "telegram",
                    "handle": handle,
                    "external_id": row.get("external_id") or "",
                    "title": row.get("title") or "",
                    "body": row.get("body") or "",
                    "image_url": row.get("image_url") or "",
                    "link": row.get("link") or "",
                    "published_at": row.get("published_at") or now,
                    "raw": row.get("raw") or {"mode": "tg_public", "handle": handle},
                }
            )

    for handle in handles.get("vk") or []:
        items.append(
            {
                "platform": "vk",
                "handle": handle,
                "external_id": f"vk-stub-{handle}-{now[:10]}",
                "title": f"Новость VK {handle}: обзор отрасли",
                "body": (
                    f"Stub-пост из сообщества {handle}. "
                    "Краткий обзор событий и их влияния на бизнес в нише."
                ),
                "image_url": "",
                "link": "",
                "published_at": now,
                "raw": {"mode": "stub", "polled_at": now},
            }
        )
    return items
