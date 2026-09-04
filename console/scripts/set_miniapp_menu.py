#!/usr/bin/env python3
"""Register Telegram Mini App menu button for Quantum office bot.

Usage (on prod):
  cd /opt/quantum-console && ./venv/bin/python scripts/set_miniapp_menu.py
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import telegram_webapp  # noqa: E402


def main() -> int:
    tok = telegram_webapp._load_bot_token()
    if not tok:
        print("ERROR: no TELEGRAM_BOT_TOKEN / MINIAPP_BOT_TOKEN", file=sys.stderr)
        return 1
    url = telegram_webapp.miniapp_public_url()
    text = os.getenv("MINIAPP_MENU_TEXT", "Каналы сегодня").strip() or "Каналы сегодня"
    payload = {
        "menu_button": {
            "type": "web_app",
            "text": text,
            "web_app": {"url": url},
        }
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{tok}/setChatMenuButton",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8")
    print(raw)
    print("menu ->", url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
