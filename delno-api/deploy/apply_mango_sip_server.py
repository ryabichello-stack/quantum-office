#!/usr/bin/env python3
"""Host-side multi-tenant SIP apply/probe for Cloud4Box.

Bind must be reachable from the delno-api container (docker0), not only loopback:
  ASTERISK_SIP_APPLY_BIND=172.17.0.1 ASTERISK_SIP_APPLY_TOKEN=... python3 apply_mango_sip_server.py

Endpoints:
  GET  /probe?tenant_slug=<slug>
  POST /apply  JSON {tenant_slug, login, password, did?}

Login format (required): Mango ``VPBX_ACCOUNT/employee`` e.g. ``123456789/ivan``.
Each tenant gets its own PJSIP registration + endpoint under pjsip.d/.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

CONF = Path(os.getenv("ASTERISK_PJSIP_CONF", "/etc/asterisk/pjsip.conf"))
PJSIP_D = Path(os.getenv("ASTERISK_PJSIP_D", "/etc/asterisk/pjsip.d"))
TOKEN = (os.getenv("ASTERISK_SIP_APPLY_TOKEN") or os.getenv("OFFICE_WEBHOOK_TOKEN") or "").strip()
BIND = os.getenv("ASTERISK_SIP_APPLY_BIND", "172.17.0.1")
PORT = int(os.getenv("ASTERISK_SIP_APPLY_PORT", "18099"))
MANGO_PROXY = os.getenv("MANGO_SIP_OUTBOUND_PROXY", "sip:81.88.86.37:5060;lr")
LEGACY_REG_NAME = os.getenv("ASTERISK_SIP_LEGACY_REG", "mango-registration")
# Probe-only fallback while a tenant conf is absent. NEVER keep this registration
# Registered alongside any delno-<slug>-reg — dual INVITEs shred Ava audio.
LEGACY_TENANT = os.getenv("ASTERISK_SIP_LEGACY_TENANT", "quantum-labs")

# Hard multi-tenant rule (owner): N cabinets, N registrations, never a shared trunk.


def _asterisk(cmd: str) -> str:
    return subprocess.check_output(["asterisk", "-rx", cmd], text=True, stderr=subprocess.STDOUT)


def _safe_slug(slug: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (slug or "").strip().lower()).strip("-")
    return (s or "tenant")[:48]


def _parse_login(login: str) -> tuple[str | None, str | None, str | None]:
    raw = (login or "").strip()
    if not raw:
        return None, None, "missing_login"
    if "/" not in raw:
        return None, None, "login_must_be_account_slash_employee"
    account, _, employee = raw.partition("/")
    account = re.sub(r"\D", "", account)
    employee = re.sub(r"[^a-zA-Z0-9._-]", "", employee.strip())
    if len(account) < 5 or not employee:
        return None, None, "login_must_be_account_slash_employee"
    return account, employee, None


def _object_names(slug: str) -> dict[str, str]:
    safe = _safe_slug(slug)
    return {
        "auth": f"delno-{safe}-auth",
        "reg": f"delno-{safe}-reg",
        "endpoint": f"delno-{safe}",
        "aor": f"delno-{safe}-aor",
    }


def _normalize_did_digits(did: str | None) -> str:
    if not did:
        return ""
    s = re.sub(r"\D", "", did)
    if s.startswith("8") and len(s) == 11:
        s = "7" + s[1:]
    return s


def _ensure_include() -> None:
    PJSIP_D.mkdir(parents=True, exist_ok=True)
    text = CONF.read_text() if CONF.exists() else ""
    marker = '#include "pjsip.d/*.conf"'
    alt = "#include pjsip.d/*.conf"
    if marker in text or alt in text:
        return
    with CONF.open("a", encoding="utf-8") as fh:
        fh.write("\n; DELNO multi-tenant SIP registrations\n")
        fh.write(f'{marker}\n')


def _set_pjsip_section_enabled(text: str, section: str, enabled: bool) -> tuple[str, bool]:
    """Insert/update ``enabled=`` in a ``[section]`` block. Returns (text, changed)."""
    header = f"[{section}]"
    if header not in text:
        return text, False
    before, _, rest = text.partition(header)
    # Section body until next top-level [section] (not nested comments).
    body, sep, after = rest.partition("\n[")
    lines = body.splitlines()
    # lines[0] is empty or leftover after header on same line — keep structure:
    # rest starts with "\n..." after partition on header without trailing newline issues.
    out_lines: list[str] = []
    saw_enabled = False
    changed = False
    want = "yes" if enabled else "no"
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("enabled="):
            saw_enabled = True
            new_line = f"enabled={want}"
            if stripped != new_line and not stripped.startswith(f"enabled={want}"):
                # preserve indent
                indent = line[: len(line) - len(line.lstrip())]
                out_lines.append(f"{indent}enabled={want}")
                changed = True
            else:
                out_lines.append(line)
        else:
            out_lines.append(line)
    if not saw_enabled:
        # Insert right after the section header line (first element is usually "").
        insert_at = 1 if out_lines and out_lines[0] == "" else 0
        out_lines.insert(insert_at, f"enabled={want}")
        changed = True
    # Preserve a trailing newline on the section body when the source had one.
    trailing_nl = body.endswith("\n")
    new_rest = "\n".join(out_lines)
    if trailing_nl and not new_rest.endswith("\n"):
        new_rest += "\n"
    if sep:
        new_text = before + header + new_rest + sep + after
    else:
        new_text = before + header + new_rest
    return new_text, changed


def _tenant_reg_files_exist() -> bool:
    if not PJSIP_D.is_dir():
        return False
    return any(PJSIP_D.glob("delno-tenant-*.conf"))


def disable_legacy_shared_registration(*, force: bool = False) -> dict:
    """Disable shared ``mango-registration`` when any per-tenant conf exists.

    Dual registration of the same Mango account (legacy + delno-<slug>-reg)
    causes two Stasis legs per inbound call and destroys Ava audio — even for
    a single customer. Multi-tenant requires exactly one registration per account.
    """
    if not force and not _tenant_reg_files_exist():
        return {"ok": True, "skipped": True, "reason": "no_tenant_regs"}
    if not CONF.exists():
        return {"ok": False, "error": "pjsip_conf_missing"}
    text = CONF.read_text()
    new_text, changed = _set_pjsip_section_enabled(text, LEGACY_REG_NAME, False)
    if changed:
        bak = CONF.with_suffix(CONF.suffix + ".bak.dualreg-guard")
        if not bak.exists():
            bak.write_text(text)
        CONF.write_text(new_text)
        try:
            _asterisk("module reload res_pjsip.so")
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"reload_failed:{exc}"[:200], "changed": True}
        try:
            _asterisk(f"pjsip send unregister {LEGACY_REG_NAME}")
        except Exception:
            pass
    return {
        "ok": True,
        "changed": changed,
        "legacy_reg": LEGACY_REG_NAME,
        "enabled": False,
        "message_ru": "Общая mango-registration отключена — только per-tenant delno-<slug>-reg.",
    }


def _tenant_conf_path(slug: str) -> Path:
    return PJSIP_D / f"delno-tenant-{_safe_slug(slug)}.conf"


def _render_tenant_conf(
    *,
    slug: str,
    account: str,
    employee: str,
    password: str,
    did_digits: str,
) -> str:
    names = _object_names(slug)
    domain = f"vpbx{account}.mangosip.ru"
    caller = did_digits or employee
    callerid = f"DELNO <{caller}>" if did_digits else f"{employee}"
    # Escape semicolon for Asterisk conf outbound_proxy
    proxy = MANGO_PROXY.replace(";", r"\;")
    return f"""\
; DELNO tenant SIP — auto-generated, do not edit by hand
; tenant={slug} account={account} employee={employee}

[{names['auth']}]
type=auth
auth_type=userpass
username={employee}
password={password}

[{names['aor']}]
type=aor
contact=sip:{domain}:5060
qualify_frequency=60

[{names['endpoint']}]
type=endpoint
transport=transport-udp
context=from-mango
disallow=all
allow=alaw
aors={names['aor']}
outbound_auth={names['auth']}
outbound_proxy={proxy}
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
dtmf_mode=rfc4733
from_user={caller}
from_domain={domain}
callerid={callerid}
trust_id_outbound=yes
send_pai=yes
send_rpid=yes
trust_id_inbound=yes
allow_unauthenticated_options=yes

[{names['reg']}]
type=registration
outbound_auth={names['auth']}
server_uri=sip:{domain}:5060
client_uri=sip:{employee}@{domain}
contact_user={employee}
expiration=300
transport=transport-udp
outbound_proxy={proxy}
line=yes
endpoint={names['endpoint']}
"""


def _status_from_regs_output(out: str, reg_name: str) -> str:
    status = "unknown"
    for line in (out or "").splitlines():
        if reg_name not in line:
            continue
        low = line.lower()
        if "rejected" in low:
            return "rejected"
        if "registered" in low:
            return "registered"
        if "unregistered" in low:
            return "unregistered"
    # Fallback: whole dump (legacy single-reg hosts)
    low = (out or "").lower()
    if reg_name == LEGACY_REG_NAME:
        if "registered" in low and "rejected" not in low:
            return "registered"
        if "rejected" in low:
            return "rejected"
        if "unregistered" in low:
            return "unregistered"
    return status


def probe(tenant_slug: str | None = None) -> dict:
    out = _asterisk("pjsip show registrations")
    slug = (tenant_slug or "").strip()
    if slug:
        reg_name = _object_names(slug)["reg"]
        status = _status_from_regs_output(out, reg_name)
        # Legacy bridge: ONLY the designated legacy tenant may read the old shared
        # mango-registration. Other cabinets must not look Registered on QL's line.
        if (
            status == "unknown"
            and slug == LEGACY_TENANT
            and not _tenant_conf_path(slug).exists()
        ):
            status = _status_from_regs_output(out, LEGACY_REG_NAME)
            if status != "unknown":
                reg_name = LEGACY_REG_NAME
    else:
        reg_name = LEGACY_REG_NAME
        status = _status_from_regs_output(out, LEGACY_REG_NAME)
    return {
        "ok": status == "registered",
        "reachable": True,
        "status": status,
        "tenant_slug": slug or None,
        "registration": reg_name,
        "trunk_id": _object_names(slug)["endpoint"] if slug else None,
        "message_ru": {
            "registered": "Линия Mango Registered.",
            "rejected": "Mango Rejected — проверьте SIP-пароль и логин вида аккаунт/сотрудник.",
            "unregistered": "Линия Unregistered.",
            "unknown": "Регистрация этого кабинета ещё не создана или не найдена.",
        }.get(status, "Статус неизвестен."),
    }


def apply(
    *,
    tenant_slug: str,
    login: str,
    password: str,
    did: str | None = None,
) -> dict:
    slug = (tenant_slug or "").strip()
    if not slug:
        return {"ok": False, "error": "tenant_slug_required"}
    account, employee, err = _parse_login(login)
    if err:
        return {
            "ok": False,
            "error": err,
            "message_ru": (
                "Нужен логин Mango вида «номер_аккаунта/сотрудник» "
                "(например 123456789/ivan), не только имя сотрудника."
            ),
        }
    if not password:
        return {"ok": False, "error": "missing_credentials"}

    _ensure_include()
    did_digits = _normalize_did_digits(did)
    conf_path = _tenant_conf_path(slug)
    bak = conf_path.with_suffix(conf_path.suffix + ".bak")
    if conf_path.exists() and not bak.exists():
        bak.write_text(conf_path.read_text())
    conf_path.write_text(
        _render_tenant_conf(
            slug=slug,
            account=account or "",
            employee=employee or "",
            password=password,
            did_digits=did_digits,
        )
    )
    # After the first (or any) per-tenant reg exists, shared legacy must die —
    # otherwise Mango forks INVITEs to both and Ava audio shreds (N≥1 clients).
    legacy_guard = disable_legacy_shared_registration(force=True)

    names = _object_names(slug)
    _asterisk("module reload res_pjsip.so")
    try:
        _asterisk(f"pjsip send register {names['reg']}")
    except Exception:
        pass
    time.sleep(2.5)
    reg = probe(slug)
    return {
        "ok": bool(reg.get("ok")),
        "applied": True,
        "tenant_slug": slug,
        "username": employee,
        "account": account,
        "trunk_id": names["endpoint"],
        "registration": reg,
        "legacy_shared_disabled": legacy_guard,
        "message_ru": reg.get("message_ru"),
    }


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
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/probe":
            return self._json(404, {"ok": False, "error": "not_found"})
        qs = parse_qs(parsed.query or "")
        slug = (qs.get("tenant_slug") or [None])[0]
        try:
            self._json(200, probe(slug))
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
            self._json(
                200,
                apply(
                    tenant_slug=str(data.get("tenant_slug") or ""),
                    login=str(data.get("login") or data.get("username") or ""),
                    password=str(data.get("password") or ""),
                    did=str(data.get("did") or "") or None,
                ),
            )
        except Exception as exc:  # noqa: BLE001
            self._json(500, {"ok": False, "error": str(exc)[:200]})

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    if not TOKEN:
        raise SystemExit("Set ASTERISK_SIP_APPLY_TOKEN or OFFICE_WEBHOOK_TOKEN")
    PJSIP_D.mkdir(parents=True, exist_ok=True)
    try:
        guard = disable_legacy_shared_registration()
        print(f"legacy_shared_registration_guard={guard}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"legacy_shared_registration_guard_error={exc}", flush=True)
    httpd = ThreadingHTTPServer((BIND, PORT), Handler)
    print(f"sip-apply listening on {BIND}:{PORT} (multi-tenant, no shared trunk)", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
