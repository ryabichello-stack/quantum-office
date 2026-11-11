"""Standalone channel-curate poller (no personal secretary).

Env:
  TELEGRAM_CHANNEL_BOT_TOKEN
  OPENAI_API_KEY / OPENAI_MODEL
  TELEGRAM_CURATE_*  (see channel_curate.py)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any

from dotenv import load_dotenv

load_dotenv()

import channel_curate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("channel-curate")

TOKEN = (os.getenv("TELEGRAM_CHANNEL_BOT_TOKEN") or "").strip()
OPENAI_API_KEY = (os.getenv("OPENAI_API_KEY") or "").strip()
OPENAI_MODEL = (os.getenv("OPENAI_MODEL") or "gpt-4.1-mini").strip()
POLL_INTERVAL_S = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1") or "1")
_stop = threading.Event()


def tg_post(
    method: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    tok = (token or TOKEN or "").strip()
    if not tok:
        raise RuntimeError("telegram_token_missing")
    url = f"https://api.telegram.org/bot{tok}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def poll_loop() -> None:
    offset: int | None = None
    logger.info(
        "curate poller start target=%s model=%s",
        channel_curate.target_channel(),
        OPENAI_MODEL,
    )
    try:
        tg_post("deleteWebhook", {"drop_pending_updates": False}, timeout=15.0)
    except Exception:
        logger.exception("deleteWebhook failed")

    while not _stop.is_set():
        if not TOKEN:
            time.sleep(5)
            continue
        try:
            payload: dict[str, Any] = {
                "timeout": 25,
                "allowed_updates": ["message", "callback_query"],
            }
            if offset is not None:
                payload["offset"] = offset
            out = tg_post("getUpdates", payload, timeout=35.0)
            if not out.get("ok"):
                logger.warning("getUpdates not ok: %s", out)
                time.sleep(3)
                continue
            for upd in out.get("result") or []:
                offset = int(upd.get("update_id", 0)) + 1
                try:
                    channel_curate.handle_update(
                        upd,
                        tg_post=tg_post,
                        openai_api_key=OPENAI_API_KEY,
                        model=OPENAI_MODEL,
                    )
                except Exception:
                    logger.exception("curate update failed: %s", upd.get("update_id"))
        except urllib.error.URLError as exc:
            logger.warning("poll error: %s", exc)
            time.sleep(3)
        except Exception:
            logger.exception("poll unexpected")
            time.sleep(3)
        time.sleep(POLL_INTERVAL_S)


def main() -> None:
    if not TOKEN:
        raise SystemExit("TELEGRAM_CHANNEL_BOT_TOKEN required")
    if not channel_curate.enabled():
        raise SystemExit("channel_curate disabled")
    if not OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY missing — will publish without rewrite until key is set")
    me = tg_post("getMe", {})
    logger.info("bot=%s", (me.get("result") or {}).get("username"))
    poll_loop()


if __name__ == "__main__":
    main()
