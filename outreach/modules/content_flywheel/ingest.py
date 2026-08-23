"""News ingest — poll watch sources (stub) + manual import."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def flywheel_enabled() -> bool:
    return (os.getenv("FLYWHEEL_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def default_source_handles() -> dict[str, list[str]]:
    return {
        "telegram": _split_csv(os.getenv("FLYWHEEL_SOURCE_TG") or os.getenv("OWNED_TG_CHANNELS") or ""),
        "vk": _split_csv(os.getenv("FLYWHEEL_SOURCE_VK") or os.getenv("OWNED_VK_GROUPS") or ""),
    }


def poll_watch_sources(*, handles: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Stub parser: one synthetic news item per configured handle.

    Real TG/VK API collectors plug in here later.
    """
    if not flywheel_enabled():
        return []
    handles = handles or default_source_handles()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    items: list[dict[str, Any]] = []
    for handle in handles.get("telegram") or []:
        items.append(
            {
                "platform": "telegram",
                "handle": handle,
                "external_id": f"tg-stub-{handle}-{now[:10]}",
                "title": f"Отраслевой тренд из {handle}",
                "body": (
                    f"Краткая выжимка (stub) из канала {handle}. "
                    "Обсуждают изменения на рынке, спрос и ключевые тренды недели."
                ),
                "image_url": "",
                "link": "",
                "published_at": now,
                "raw": {"mode": "stub", "polled_at": now},
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
