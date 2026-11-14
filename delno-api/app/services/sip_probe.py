"""Probe / apply Mango SIP on the host Asterisk — multi-tenant.

Each tenant saves ``mango_sip`` (login ``VPBX_ACCOUNT/employee`` + SIP password).
Apply creates a dedicated PJSIP registration/endpoint for that tenant via the
host helper (`apply_mango_sip_server.py`). Never reuse another tenant's trunk.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

CURSOR_TASK_SIP_REJECTED = """# Task for Cursor — Mango SIP registration Rejected

## Context
- Host: Cloud4Box Asterisk PJSIP (per-tenant `delno-<slug>-reg`)
- Tenant vault has `mango_sip`; apply path: `delno-api` → host SIP apply helper

## Do
1. Confirm login is Mango ``VPBX_ACCOUNT/employee`` (not web UI login) and password is the **SIP** password.
2. Confirm DID is provisioned for THIS tenant (`phones.provision`) — never assume a shared dogfood number.
3. Re-save via Hermes vault form (triggers per-tenant apply) or POST host `/apply` with tenant_slug.
4. `pjsip show registrations` → expect **Registered** on `delno-<slug>-reg`.
5. Smoke inbound to the tenant's own DID.

## Done when
Tenant-specific registration is Registered and inbound on that DID routes to the tenant.
"""


def parse_mango_login(login: str) -> dict[str, str | None]:
    """Split ``account/employee``; account digits-only, employee SIP user."""
    raw = (login or "").strip()
    if not raw:
        return {"account": None, "employee": None, "error": "missing_login"}
    if "/" not in raw:
        return {
            "account": None,
            "employee": raw,
            "error": "login_must_be_account_slash_employee",
        }
    account, _, employee = raw.partition("/")
    account_n = re.sub(r"\D", "", account)
    employee_n = re.sub(r"[^a-zA-Z0-9._-]", "", employee.strip())
    if len(account_n) < 5 or not employee_n:
        return {
            "account": account_n or None,
            "employee": employee_n or None,
            "error": "login_must_be_account_slash_employee",
        }
    return {"account": account_n, "employee": employee_n, "error": None}


def trunk_id_for_tenant(tenant_slug: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "-", (tenant_slug or "").strip().lower()).strip("-") or "tenant"
    return f"delno-{safe[:48]}"


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


def probe_registration(tenant_slug: str | None = None) -> dict[str, Any]:
    """Read THIS tenant's registration status (never another cabinet's line)."""
    apply_url = (os.getenv("ASTERISK_SIP_APPLY_URL") or "").strip()
    if apply_url:
        q = ""
        if tenant_slug:
            q = "?" + urllib.parse.urlencode({"tenant_slug": tenant_slug})
        return _probe_via_http(apply_url.rstrip("/") + "/probe" + q)

    slug = (tenant_slug or "").strip()
    reg_name = f"{trunk_id_for_tenant(slug)}-reg" if slug else "mango-registration"
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
    for line in out.splitlines():
        if reg_name not in line:
            continue
        lower = line.lower()
        if "rejected" in lower:
            status = "rejected"
            break
        if "registered" in lower:
            status = "registered"
            break
        if "unregistered" in lower:
            status = "unregistered"
            break
    return {
        "ok": status == "registered",
        "reachable": True,
        "status": status,
        "tenant_slug": slug or None,
        "detail": reg_name,
        "trunk_id": trunk_id_for_tenant(slug) if slug else None,
        "message_ru": _status_message(status),
        "raw_excerpt": _safe_excerpt(out),
    }


def apply_mango_sip(
    *,
    tenant_slug: str,
    login: str,
    password: str,
    did: str | None = None,
) -> dict[str, Any]:
    """Push THIS tenant's credentials to a dedicated Asterisk registration."""
    slug = (tenant_slug or "").strip()
    if not slug:
        return {"ok": False, "error": "tenant_slug_required"}
    parsed = parse_mango_login(login)
    if parsed.get("error"):
        return {
            "ok": False,
            "error": parsed["error"],
            "message_ru": (
                "Нужен логин Mango вида «номер_аккаунта/сотрудник» "
                "(из карточки SIP сотрудника), не пароль веб-кабинета."
            ),
        }
    if not password:
        return {"ok": False, "error": "missing_credentials"}

    apply_url = (os.getenv("ASTERISK_SIP_APPLY_URL") or "").strip()
    if apply_url:
        return _apply_via_http(
            apply_url.rstrip("/") + "/apply",
            tenant_slug=slug,
            login=login,
            password=password,
            did=did,
        )

    # Local CLI path (host process) — write via helper logic is preferred;
    # without HTTP helper we cannot safely mutate shared pjsip.conf for N tenants.
    return {
        "ok": False,
        "error": "apply_url_required",
        "message_ru": (
            "SIP сохранён в сейфе, но хост-helper apply URL не настроен "
            "(ASTERISK_SIP_APPLY_URL). Линию для кабинета не регистрирую."
        ),
    }


def after_vault_sip_save(
    *,
    tenant_slug: str,
    login: str | None,
    password: str | None,
    did: str | None = None,
) -> dict[str, Any]:
    """Called after tenant vault mango_sip save — apply+probe for THIS tenant only."""
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

    # Multi-tenant: every cabinet may apply. Legacy ASTERISK_SIP_APPLY_TENANT_SLUG
    # is ignored (was a dogfood single-line gate).
    if not enabled:
        probe = probe_registration(tenant_slug)
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
    return apply_mango_sip(
        tenant_slug=tenant_slug,
        login=login or "",
        password=password,
        did=did,
    )


def _next_actions(probe: dict[str, Any]) -> list[dict[str, str]]:
    if probe.get("ok"):
        return [
            {"title": "Тестовый звонок", "text": "Сделай тестовый входящий на наш DID"},
            {"title": "Голос", "text": "Какой голос Realtime сейчас?"},
            {"title": "Здоровье", "text": "Проверь здоровье офиса"},
        ]
    return [
        {
            "title": "Форма SIP ещё раз",
            "text": "Открой безопасную форму SIP — логин аккаунт/сотрудник и SIP-пароль Mango",
        },
        {"title": "DID", "text": "Привяжи номер DID этого кабинета"},
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
        if any(k in line for k in ("delno-", "mango", "Registration", "Status", "Registered", "Rejected", "Objects")):
            lines.append(line[:160])
    return "\n".join(lines[:8])


def _apply_via_http(
    url: str,
    *,
    tenant_slug: str,
    login: str,
    password: str,
    did: str | None = None,
) -> dict[str, Any]:
    token = (os.getenv("ASTERISK_SIP_APPLY_TOKEN") or os.getenv("OFFICE_WEBHOOK_TOKEN") or "").strip()
    body = json.dumps(
        {
            "tenant_slug": tenant_slug,
            "login": login,
            "username": login,  # back-compat with older helpers
            "password": password,
            "did": did or "",
        }
    ).encode()
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
        probe = probe_registration(tenant_slug)
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
