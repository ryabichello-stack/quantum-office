"""Probe / apply Mango SIP on the host Asterisk (dogfood / single-host).

Vault save alone is not enough — Asterisk must get the password and re-register.
Enabled only when ASTERISK_SIP_APPLY_URL or local CLI is configured.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

CURSOR_TASK_SIP_REJECTED = """# Task for Cursor — Mango SIP registration Rejected

## Context
- Host: Cloud4Box (`161.104.89.123`)
- Asterisk PJSIP registration `mango-registration` → `vpbx400348777.mangosip.ru` status **Rejected**
- Tenant vault has `mango_sip` credentials; apply path: `delno-api` → Asterisk `mango-auth`

## Do
1. Confirm login format is Mango employee `номер/сотрудник` (e.g. `400348777/garik`) and password is the **SIP** password from Mango (not web UI).
2. Apply via vault form in Hermes or `/opt/delno/scripts/apply_mango_sip.py`.
3. `asterisk -rx "pjsip send register mango-registration"` then `pjsip show registrations` → expect **Registered**.
4. Smoke: inbound to DID / `quantum_sip_test_call.py` if available.
5. Do **not** SSH to destroyed Beget `5.35.86.62`.

## Done when
`pjsip show registrations` shows Registered and a test call reaches AVA (`openai_realtime` / cedar).
"""


def _run_asterisk(cmd: str, timeout: float = 8.0) -> tuple[bool, str]:
    try:
        out = subprocess.check_output(
            ["asterisk", "-rx", cmd],
            stderr=subprocess.STDOUT,
            timeout=timeout,
            text=True,
        )
        return True, out
    except FileNotFoundError:
        return False, "asterisk_cli_missing"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:300]


def probe_registration() -> dict[str, Any]:
    """Read current mango-registration status without secrets."""
    apply_url = (os.getenv("ASTERISK_SIP_APPLY_URL") or "").strip()
    if apply_url:
        return _probe_via_http(apply_url.rstrip("/") + "/probe")

    ok, out = _run_asterisk("pjsip show registrations")
    if not ok:
        return {
            "ok": False,
            "reachable": False,
            "status": "unknown",
            "detail": out,
            "message_ru": "Не удалось спросить Asterisk о регистрации SIP.",
        }
    status = "unknown"
    lower = out.lower()
    if "registered" in lower and "rejected" not in lower:
        status = "registered"
    elif "rejected" in lower:
        status = "rejected"
    elif "unregistered" in lower or "exp." in lower:
        status = "unregistered"
    return {
        "ok": status == "registered",
        "reachable": True,
        "status": status,
        "detail": "mango-registration",
        "message_ru": _status_message(status),
        "raw_excerpt": _safe_excerpt(out),
    }


def apply_mango_sip(*, username: str, password: str) -> dict[str, Any]:
    """Push credentials to Asterisk auth objects and request re-register."""
    user = (username or "").strip()
    if "/" in user:
        user = user.split("/", 1)[-1].strip()
    if not user or not password:
        return {"ok": False, "error": "missing_credentials"}

    apply_url = (os.getenv("ASTERISK_SIP_APPLY_URL") or "").strip()
    if apply_url:
        return _apply_via_http(apply_url.rstrip("/") + "/apply", user=user, password=password)

    # Local CLI path (host process, not typical inside API container)
    conf = os.getenv("ASTERISK_PJSIP_CONF", "/etc/asterisk/pjsip.conf")
    try:
        path_ok = _patch_pjsip_file(conf, user=user, password=password)
        if not path_ok.get("ok"):
            return path_ok
        _run_asterisk("module reload res_pjsip.so")
        _run_asterisk("pjsip send register mango-registration")
    except Exception as exc:  # noqa: BLE001
        logger.exception("sip apply failed")
        return {"ok": False, "error": "apply_failed", "detail": str(exc)[:200]}

    import time

    time.sleep(2.5)
    probe = probe_registration()
    return {
        "ok": bool(probe.get("ok")),
        "applied": True,
        "username": user,
        "registration": probe,
        "message_ru": probe.get("message_ru"),
        "cursor_task": None if probe.get("ok") else CURSOR_TASK_SIP_REJECTED,
        "next_actions": _next_actions(probe),
    }


def after_vault_sip_save(*, tenant_slug: str, login: str | None, password: str | None) -> dict[str, Any]:
    """Called after tenant vault mango_sip save — apply+probe when enabled."""
    # Legacy apply endpoint edits one shared Asterisk profile. Never send another
    # tenant's SIP credentials there until the endpoint routes by tenant/DID.
    allowed_tenant = (os.getenv("ASTERISK_SIP_APPLY_TENANT_SLUG") or "").strip()
    if not allowed_tenant or tenant_slug != allowed_tenant:
        return {
            "ok": False,
            "skipped": True,
            "reason": "tenant_route_not_configured",
            "message_ru": "SIP сохранён. Для этой компании ещё не настроен отдельный маршрут телефонии; общую линию не меняю.",
        }
    try:
        from app.core.config import get_settings

        settings = get_settings()
        enabled = bool(getattr(settings, "asterisk_sip_apply_enabled", False))
        url = (getattr(settings, "asterisk_sip_apply_url", None) or "").strip()
        if url:
            os.environ["ASTERISK_SIP_APPLY_URL"] = url
            enabled = True
    except Exception:  # noqa: BLE001
        enabled = (os.getenv("ASTERISK_SIP_APPLY_ENABLED") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        url = (os.getenv("ASTERISK_SIP_APPLY_URL") or "").strip()
    if not enabled:
        probe = probe_registration()
        return {
            "ok": False,
            "skipped": True,
            "reason": "apply_disabled",
            "registration": probe,
            "message_ru": (
                "SIP сохранён в сейфе. Автоприменение к Asterisk выключено "
                "(ASTERISK_SIP_APPLY_ENABLED). Статус линии: "
                + str(probe.get("message_ru") or "неизвестен")
            ),
            "cursor_task": None if probe.get("ok") else CURSOR_TASK_SIP_REJECTED,
            "next_actions": _next_actions(probe),
        }
    if not password:
        return {"ok": False, "error": "password_required_for_apply"}
    return apply_mango_sip(username=login or "", password=password)


def _next_actions(probe: dict[str, Any]) -> list[dict[str, str]]:
    if probe.get("ok"):
        return [
            {"title": "Тестовый звонок", "text": "Сделай тестовый входящий/исходящий звонок на наш DID"},
            {"title": "Голос", "text": "Какой голос Realtime сейчас? Смени на cedar"},
            {"title": "Здоровье", "text": "Проверь здоровье офиса"},
        ]
    return [
        {"title": "Форма SIP ещё раз", "text": "Открой безопасную форму SIP — логин номер/сотрудник и SIP-пароль Mango"},
        {"title": "Задание Cursor", "text": "Дай задание для Cursor: починить Mango SIP registration Rejected"},
        {"title": "Статус линии", "text": "Проверь регистрацию SIP и здоровье телефонии"},
    ]


def _status_message(status: str) -> str:
    return {
        "registered": "Линия Mango зарегистрирована (Registered) — можно делать тестовый звонок.",
        "rejected": "Mango отклонил регистрацию (Rejected) — логин/SIP-пароль или провижининг.",
        "unregistered": "Линия не зарегистрирована.",
        "unknown": "Статус регистрации SIP неизвестен.",
    }.get(status, "Статус регистрации SIP неизвестен.")


def _safe_excerpt(raw: str) -> str:
    lines = []
    for line in (raw or "").splitlines():
        if "password" in line.lower():
            continue
        if any(k in line for k in ("mango", "Registration", "Status", "Registered", "Rejected", "Objects")):
            lines.append(line[:160])
    return "\n".join(lines[:8])


def _patch_pjsip_file(path: str, *, user: str, password: str) -> dict[str, Any]:
    from pathlib import Path

    p = Path(path)
    if not p.exists():
        return {"ok": False, "error": "pjsip_conf_missing", "path": path}
    text = p.read_text()
    bak = p.with_suffix(p.suffix + ".bak.hermes_sip")
    if not bak.exists():
        bak.write_text(text)
    lines = text.splitlines(True)
    out: list[str] = []
    in_sec = False
    target_secs = {"mango-auth", "mango-employee-auth"}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_sec = stripped[1:-1] in target_secs
            out.append(line)
            continue
        if in_sec and stripped.startswith("username="):
            out.append(f"username={user}\n")
            continue
        if in_sec and stripped.startswith("password="):
            out.append(f"password={password}\n")
            continue
        out.append(line)
    new = "".join(out)
    if re.search(r"password=__MANGO_SIP_PASSWORD__", new):
        return {"ok": False, "error": "placeholder_remains"}
    p.write_text(new)
    return {"ok": True}


def _apply_via_http(url: str, *, user: str, password: str) -> dict[str, Any]:
    token = (os.getenv("ASTERISK_SIP_APPLY_TOKEN") or os.getenv("OFFICE_WEBHOOK_TOKEN") or "").strip()
    body = json.dumps({"username": user, "password": password}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Token": token,
        },
        method="POST",
    )
    try:
        with _no_proxy_opener().open(req, timeout=20) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        return {"ok": False, "error": "apply_http_failed", "detail": str(exc)[:200]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": "apply_http_failed", "detail": str(exc)[:200]}
    probe = data.get("registration") if isinstance(data, dict) else None
    if not isinstance(probe, dict):
        probe = probe_registration()
    data = dict(data) if isinstance(data, dict) else {"ok": False}
    data.setdefault("next_actions", _next_actions(probe))
    if not data.get("ok"):
        data.setdefault("cursor_task", CURSOR_TASK_SIP_REJECTED)
    return data


def _no_proxy_opener() -> urllib.request.OpenerDirector:
    """Host SIP helper must not go through OPENAI/HTTP_PROXY (would 503)."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _probe_via_http(url: str) -> dict[str, Any]:
    token = (os.getenv("ASTERISK_SIP_APPLY_TOKEN") or os.getenv("OFFICE_WEBHOOK_TOKEN") or "").strip()
    req = urllib.request.Request(url, headers={"X-Webhook-Token": token}, method="GET")
    try:
        with _no_proxy_opener().open(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "reachable": False,
            "status": "unknown",
            "detail": str(exc)[:200],
            "message_ru": "Не удалось получить статус SIP с хоста.",
        }
