"""Optional client: queue welcome PDF email via ava-mailer after calendar create."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict

logger = logging.getLogger(__name__)

MAILER_BASE_URL = os.getenv("MAILER_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
MAILER_WEBHOOK_TOKEN = os.getenv(
    "MAILER_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")
).strip()
MAILER_TIMEOUT_SECONDS = float(os.getenv("MAILER_TIMEOUT_SECONDS", "10") or "10")
WELCOME_VIA_MAILER = os.getenv("WELCOME_VIA_MAILER", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def queue_welcome_presentation(
    *,
    attendee_email: str,
    summary: str = "",
    description: str = "",
    meeting_start: str = "",
    telemost_join_url: str = "",
) -> Dict[str, Any]:
    """Best-effort POST to mailer /api/welcome/presentation. Soft-fails."""
    if not WELCOME_VIA_MAILER:
        return {"ok": False, "skipped": True, "reason": "disabled"}
    email = (attendee_email or "").strip()
    if not email:
        return {"ok": False, "skipped": True, "reason": "no_attendee_email"}
    if not MAILER_BASE_URL:
        return {"ok": False, "skipped": True, "reason": "no_mailer_base"}

    payload = {
        "attendee_email": email,
        "summary": summary or "",
        "description": description or "",
        "meeting_start": meeting_start or "",
        "telemost_join_url": telemost_join_url or "",
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if MAILER_WEBHOOK_TOKEN:
        headers["X-Webhook-Token"] = MAILER_WEBHOOK_TOKEN
    req = urllib.request.Request(
        f"{MAILER_BASE_URL}/api/welcome/presentation",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=MAILER_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(body) if body else {}
            except Exception:
                parsed = {"raw": body}
            if not isinstance(parsed, dict):
                parsed = {"raw": parsed}
            parsed.setdefault("ok", True)
            return parsed
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
        logger.warning("[WELCOME] mailer HTTP %s: %s", exc.code, err[:300])
        return {"ok": False, "error": f"http_{exc.code}", "detail": err[:300]}
    except Exception as exc:
        logger.warning("[WELCOME] mailer call failed: %s", exc)
        return {"ok": False, "error": str(exc)}
