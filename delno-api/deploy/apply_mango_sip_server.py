#!/usr/bin/env python3
"""Host-side SIP apply/probe for Cloud4Box.

Bind must be reachable from the delno-api container (docker0), not only loopback:
  ASTERISK_SIP_APPLY_BIND=172.17.0.1 ASTERISK_SIP_APPLY_TOKEN=... python3 apply_mango_sip_server.py

Endpoints:
  GET  /probe
  POST /apply  JSON {username, password}
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CONF = Path(os.getenv("ASTERISK_PJSIP_CONF", "/etc/asterisk/pjsip.conf"))
TOKEN = (os.getenv("ASTERISK_SIP_APPLY_TOKEN") or os.getenv("OFFICE_WEBHOOK_TOKEN") or "").strip()
# Default docker0 so containers via host.docker.internal can probe/apply.
BIND = os.getenv("ASTERISK_SIP_APPLY_BIND", "172.17.0.1")
PORT = int(os.getenv("ASTERISK_SIP_APPLY_PORT", "18099"))


def _asterisk(cmd: str) -> str:
    return subprocess.check_output(["asterisk", "-rx", cmd], text=True, stderr=subprocess.STDOUT)


def probe() -> dict:
    out = _asterisk("pjsip show registrations")
    status = "unknown"
    low = out.lower()
    if "registered" in low and "rejected" not in low:
        status = "registered"
    elif "rejected" in low:
        status = "rejected"
    elif "unregistered" in low:
        status = "unregistered"
    return {
        "ok": status == "registered",
        "reachable": True,
        "status": status,
        "message_ru": {
            "registered": "Линия Mango Registered.",
            "rejected": "Mango Rejected — проверьте SIP-пароль.",
            "unregistered": "Линия Unregistered.",
        }.get(status, "Статус неизвестен."),
    }


def apply(username: str, password: str) -> dict:
    user = username.split("/")[-1].strip() if username else ""
    if not user or not password:
        return {"ok": False, "error": "missing_credentials"}
    text = CONF.read_text()
    bak = CONF.with_suffix(".conf.bak.hermes_sip")
    if not bak.exists():
        bak.write_text(text)
    lines = text.splitlines(True)
    out = []
    in_sec = False
    targets = {"mango-auth", "mango-employee-auth"}
    for line in lines:
        st = line.strip()
        if st.startswith("[") and st.endswith("]"):
            in_sec = st[1:-1] in targets
            out.append(line)
            continue
        if in_sec and st.startswith("username="):
            out.append(f"username={user}\n")
            continue
        if in_sec and st.startswith("password="):
            out.append(f"password={password}\n")
            continue
        out.append(line)
    new = "".join(out)
    if "__MANGO_SIP_PASSWORD__" in new:
        return {"ok": False, "error": "placeholder_remains"}
    CONF.write_text(new)
    _asterisk("module reload res_pjsip.so")
    try:
        _asterisk("pjsip send register mango-registration")
    except Exception:
        pass
    time.sleep(2.5)
    reg = probe()
    return {"ok": bool(reg.get("ok")), "applied": True, "username": user, "registration": reg, "message_ru": reg.get("message_ru")}


class Handler(BaseHTTPRequestHandler):
    def _auth(self) -> bool:
        return bool(TOKEN) and self.headers.get("X-Webhook-Token") == TOKEN

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if not self._auth():
            return self._json(401, {"ok": False, "error": "unauthorized"})
        if self.path.rstrip("/") != "/probe":
            return self._json(404, {"ok": False, "error": "not_found"})
        try:
            self._json(200, probe())
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(exc)[:200]})

    def do_POST(self) -> None:  # noqa: N802
        if not self._auth():
            return self._json(401, {"ok": False, "error": "unauthorized"})
        if self.path.rstrip("/") != "/apply":
            return self._json(404, {"ok": False, "error": "not_found"})
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode() or "{}")
        except json.JSONDecodeError:
            return self._json(400, {"ok": False, "error": "bad_json"})
        try:
            self._json(200, apply(str(data.get("username") or ""), str(data.get("password") or "")))
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(exc)[:200]})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set ASTERISK_SIP_APPLY_TOKEN or OFFICE_WEBHOOK_TOKEN")
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"sip-apply listening on {BIND}:{PORT}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
