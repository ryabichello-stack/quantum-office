"""Yandex Telemost conference creation."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Optional, Tuple

import yandex_oauth

logger = logging.getLogger(__name__)

TELEMOST_ENABLED = os.getenv("TELEMOST_ENABLED", "true").lower() in ("1", "true", "yes", "on")
TELEMOST_WAITING_ROOM_LEVEL = os.getenv("TELEMOST_WAITING_ROOM_LEVEL", "PUBLIC").strip() or "PUBLIC"
TELEMOST_API_URL = os.getenv(
    "TELEMOST_API_URL",
    "https://cloud-api.yandex.net/v1/telemost-api/conferences",
).strip()
TELEMOST_TIMEOUT_SECONDS = float(os.getenv("TELEMOST_TIMEOUT_SECONDS", "6") or "6")


def create_conference(
    *,
    title: str = "",
    waiting_room_level: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Create a Yandex Telemost conference.

    Returns (conference_id, join_url, error_code).
    error_code is None on success.
    """
    if not TELEMOST_ENABLED:
        return None, None, "telemost_disabled"

    access_token = yandex_oauth.get_access_token()
    if not access_token:
        logger.warning(
            "[TELEMOST] no OAuth access token — authorize via /oauth/yandex/start"
        )
        return None, None, "oauth_missing"

    level = (waiting_room_level or TELEMOST_WAITING_ROOM_LEVEL).strip() or "PUBLIC"
    payload = {"waiting_room_level": level}
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        TELEMOST_API_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"OAuth {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=TELEMOST_TIMEOUT_SECONDS) as response:
            raw = response.read().decode("utf-8", errors="replace")
            data = json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("[TELEMOST HTTP ERROR] status=%s body=%s", exc.code, err_body[:500])
        return None, None, f"http_{exc.code}"
    except Exception as exc:
        logger.exception("[TELEMOST ERROR] %s", exc)
        return None, None, "telemost_error"

    conference_id = str(data.get("id") or "").strip() or None
    join_url = str(data.get("join_url") or "").strip() or None
    if not join_url:
        logger.error("[TELEMOST] API response missing join_url: %s", data)
        return conference_id, None, "missing_join_url"

    logger.info(
        "[TELEMOST] created id=%s join_url=%s title=%r",
        conference_id,
        join_url,
        (title or "")[:80],
    )
    return conference_id, join_url, None
