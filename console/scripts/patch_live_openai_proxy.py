#!/usr/bin/env python3
"""Route OpenAI Live WSS via AVA_OPENAI_PROXY (set in /root/ava/.env — never commit secrets).

Minsk HTTP proxy measured ~0.5s to api.openai.com vs ~9s direct.
Do NOT set global HTTPS_PROXY (breaks ARI / local WS).
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

LIVE = Path("/root/ava/src/providers/openai_live.py")


def main() -> int:
    src = LIVE.read_text(encoding="utf-8")
    if "_live_ws_proxy" in src and '**({"proxy": _proxy}' in src:
        print("already proxied")
        return 0
    needle = 'LIVE_WS_URL = "wss://api.openai.com/v1/live/sessions"\n'
    if needle not in src:
        print("LIVE_WS_URL missing", file=sys.stderr)
        return 1
    helper = (
        'LIVE_WS_URL = "wss://api.openai.com/v1/live/sessions"\n\n'
        "def _live_ws_proxy():\n"
        '    """Route Live WSS via AVA_OPENAI_PROXY when set (VPN edge)."""\n'
        '    for key in ("AVA_OPENAI_PROXY",):\n'
        '        val = (os.getenv(key) or "").strip()\n'
        "        if val:\n"
        "            return val\n"
        "    return None\n\n"
    )
    src = src.replace(needle, helper, 1)
    old = (
        "        self.websocket = await websockets.connect(\n"
        "            LIVE_WS_URL,\n"
        "            additional_headers=headers,\n"
        "            max_size=8 * 1024 * 1024,\n"
        "        )"
    )
    new = (
        "        _proxy = _live_ws_proxy()\n"
        "        self.websocket = await websockets.connect(\n"
        "            LIVE_WS_URL,\n"
        "            additional_headers=headers,\n"
        "            max_size=8 * 1024 * 1024,\n"
        '            **({"proxy": _proxy} if _proxy else {}),\n'
        "        )"
    )
    if old not in src:
        print("connect needle missing", file=sys.stderr)
        return 1
    src = src.replace(old, new)
    LIVE.write_text(src, encoding="utf-8")
    ast.parse(src)
    print("OK proxy helper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
