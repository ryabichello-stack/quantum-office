"""Publish adapters — stub queue only (APPROVAL_REQUIRED, never cold DM)."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("ava-outreach.social_publish.adapters")


def publish_enabled() -> bool:
    return (os.getenv("SOCIAL_PUBLISH_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def publish_to_channel(
    *,
    platform: str,
    channel_handle: str,
    text: str,
    image_path: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue or stub-publish to one owned channel. Real API wiring per platform later."""
    p = (platform or "").strip().lower()
    handle = (channel_handle or "").strip()
    enabled = publish_enabled()
    mode = "stub_queued"
    note = "SOCIAL_PUBLISH_ENABLED=false — очередь без реального API"
    external_id = None

    if enabled:
        mode = "queued"
        note = f"Очередь publish принята для {p} → {handle} (API stub)"
        external_id = f"{p}-pending-{handle.lstrip('@')[:24]}"

    return {
        "ok": True,
        "platform": p,
        "channel": handle,
        "mode": mode,
        "external_id": external_id,
        "image_attached": bool(image_path),
        "note": note,
        "auto_publish": False,
        "meta": meta or {},
    }
