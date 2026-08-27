"""Fire owner alerts via ava-text-bot (Telegram + Max fan-out).

Env:
  OWNER_ALERT_URL=http://127.0.0.1:8011/api/owner-alert
  OWNER_ALERT_TOKEN=   — same as text-bot OFFICE_WEBHOOK_TOKEN
  OWNER_ALERT_ENABLED=true
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Optional

logger = logging.getLogger("ava-mailer.owner_alert")


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
    payload = {
        "kind": kind,
        "title": title,
        "body": body,
        "meta": meta or {},
        "dedupe_key": dedupe_key,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Webhook-Token"] = token
    req = urllib.request.Request(url, data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10.0) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:300]
        logger.warning("owner alert HTTP %s: %s", exc.code, err)
        return {"ok": False, "status": exc.code, "error": err}
    except Exception as exc:  # noqa: BLE001
        logger.warning("owner alert failed: %s", exc)
        return {"ok": False, "error": str(exc)[:300]}
