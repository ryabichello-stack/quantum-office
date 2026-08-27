"""Fire owner alerts via ava-text-bot (Telegram + Max fan-out).

Env:
  OWNER_ALERT_URL=http://127.0.0.1:8011/api/owner-alert
  OWNER_ALERT_TOKEN=   — same as text-bot OFFICE_WEBHOOK_TOKEN
  OWNER_ALERT_ENABLED=true
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx

logger = logging.getLogger("ava-outreach.owner_alert")


def enabled() -> bool:
    return (os.getenv("OWNER_ALERT_ENABLED", "true") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def notify_owner(
    *,
    kind: str,
    title: str = "",
    body: str = "",
    meta: Optional[dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "skipped": "disabled"}
    url = (
        os.getenv("OWNER_ALERT_URL") or "http://127.0.0.1:8011/api/owner-alert"
    ).strip()
    token = (
        os.getenv("OWNER_ALERT_TOKEN")
        or os.getenv("OFFICE_WEBHOOK_TOKEN")
        or os.getenv("WEBHOOK_TOKEN")
        or ""
    ).strip()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Webhook-Token"] = token
    payload = {
        "kind": kind,
        "title": title,
        "body": body,
        "meta": meta or {},
        "dedupe_key": dedupe_key,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            data = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                logger.warning(
                    "owner alert HTTP %s: %s",
                    resp.status_code,
                    str(data)[:300],
                )
                return {"ok": False, "status": resp.status_code, "error": data}
            return data if isinstance(data, dict) else {"ok": True, "raw": data}
    except Exception as exc:  # noqa: BLE001
        logger.warning("owner alert failed: %s", exc)
        return {"ok": False, "error": str(exc)[:300]}
