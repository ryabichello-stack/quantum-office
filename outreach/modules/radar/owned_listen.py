"""Owned-page listening stub — TG/VK public signals → Radar (never auto-outreach).

Env:
  OWNED_LISTEN_ENABLED=0|1
  OWNED_TG_CHANNELS=@channel1,@channel2   (comma-separated)
  OWNED_VK_GROUPS=group_screen_name,...

Without API credentials this produces reviewable stub signals from configured handles
so operators can wire real collectors later.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("ava-outreach.radar.owned_listen")


def is_enabled() -> bool:
    return (os.getenv("OWNED_LISTEN_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _enabled() -> bool:
    return is_enabled()


def _split_csv(raw: str) -> list[str]:
    return [p.strip() for p in (raw or "").split(",") if p.strip()]


def configured_sources() -> dict[str, list[str]]:
    return {
        "telegram": _split_csv(os.getenv("OWNED_TG_CHANNELS") or ""),
        "vk": _split_csv(os.getenv("OWNED_VK_GROUPS") or ""),
    }


def poll_owned_pages(*, dry_run: bool = False) -> dict[str, Any]:
    """Collect best-effort owned-page hints as Radar-ready signal payloads.

    Never sends DM / cold outreach. Real TG/VK API fetch is optional later;
    when disabled or empty config, returns ok with zero items.
    """
    sources = configured_sources()
    items: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if not _enabled():
        return {
            "ok": True,
            "enabled": False,
            "items": [],
            "ingested": 0,
            "note": "OWNED_LISTEN_ENABLED is off",
        }

    for handle in sources["telegram"]:
        items.append(
            {
                "signal_type": "owned_page_activity",
                "source": "owned_telegram",
                "company_title": "",
                "summary": f"Owned TG {handle}: активность канала (stub poll {now})",
                "score": 0.45,
                "evidence": {
                    "platform": "telegram",
                    "handle": handle,
                    "mode": "stub",
                    "polled_at": now,
                },
            }
        )

    for handle in sources["vk"]:
        items.append(
            {
                "signal_type": "owned_page_activity",
                "source": "owned_vk",
                "company_title": "",
                "summary": f"Owned VK {handle}: активность сообщества (stub poll {now})",
                "score": 0.45,
                "evidence": {
                    "platform": "vk",
                    "handle": handle,
                    "mode": "stub",
                    "polled_at": now,
                },
            }
        )

    ingested = 0
    stored: list[dict[str, Any]] = []
    if not dry_run and items:
        try:
            from modules.radar import RadarStore

            store = RadarStore()
            for payload in items:
                row = store.ingest(
                    signal_type=payload["signal_type"],
                    summary=payload["summary"],
                    source=payload["source"],
                    company_title=payload.get("company_title") or "",
                    score=float(payload.get("score") or 0.45),
                    evidence=payload.get("evidence") or {},
                )
                stored.append(row)
                ingested += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("owned_listen ingest failed: %s", exc)
            return {
                "ok": False,
                "enabled": True,
                "error": str(exc)[:200],
                "items": items,
                "ingested": ingested,
            }

    return {
        "ok": True,
        "enabled": True,
        "sources": sources,
        "items": stored if stored else items,
        "ingested": ingested,
        "auto_outreach": False,
        "note": "Stub collector — wire Bot API / VK API when credentials exist",
    }
