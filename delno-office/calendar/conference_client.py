"""Optional client for the standalone conference (Telemost) service."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

CONFERENCE_BASE_URL = os.getenv("CONFERENCE_BASE_URL", "http://127.0.0.1:8016").rstrip("/")
CONFERENCE_WEBHOOK_TOKEN = os.getenv("CONFERENCE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()
CONFERENCE_TIMEOUT_SECONDS = float(os.getenv("CONFERENCE_TIMEOUT_SECONDS", "30") or "30")
CREATE_TELEMOST_BY_DEFAULT = os.getenv("CREATE_TELEMOST_BY_DEFAULT", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def create_telemost(
    *,
    title: str,
    invitees: Optional[list] = None,
    when_text: str = "",
    message: str = "",
    send_invites: bool = False,
) -> Dict[str, Any]:
    """
    Call conference service. Returns dict with ok/join_url/error.
    Does not raise on soft failures.
    """
    payload = {
        "title": title,
        "invitees": invitees or [],
        "when_text": when_text,
        "message": message,
        "send_invites": send_invites,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if CONFERENCE_WEBHOOK_TOKEN:
        headers["X-Webhook-Token"] = CONFERENCE_WEBHOOK_TOKEN

    req = urllib.request.Request(
        f"{CONFERENCE_BASE_URL}/api/conferences",
        data=body,
        method="POST",
        headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=CONFERENCE_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
            return data if isinstance(data, dict) else {"ok": False, "error": "bad_response"}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")
        logger.error("conference service HTTP %s: %s", exc.code, err[:400])
        try:
            return json.loads(err)
        except Exception:
            return {"ok": False, "error": f"http_{exc.code}"}
    except Exception as exc:
        logger.exception("conference service call failed: %s", exc)
        return {"ok": False, "error": "conference_unreachable"}
