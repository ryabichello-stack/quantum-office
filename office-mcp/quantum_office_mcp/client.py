"""HTTP clients for Quantum Office services (no third-party deps)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def console_base() -> str:
    return _env("CONSOLE_BASE", "http://127.0.0.1:8013").rstrip("/")


def campaign_base() -> str:
    return _env("CAMPAIGN_BASE", "http://127.0.0.1:8018").rstrip("/")


def knowledge_base() -> str:
    return _env(
        "AVA_KNOWLEDGE_BASE",
        _env("KNOWLEDGE_BASE", "http://127.0.0.1:8017"),
    ).rstrip("/")


def calendar_base() -> str:
    return _env("CALENDAR_BASE", "http://127.0.0.1:8014").rstrip("/")


def outreach_base() -> str:
    return _env("OUTREACH_BASE", "http://127.0.0.1:8012").rstrip("/")


def conference_base() -> str:
    return _env("CONFERENCE_BASE", "http://127.0.0.1:8016").rstrip("/")


def files_base() -> str:
    return _env("FILES_BASE", "http://127.0.0.1:8015").rstrip("/")


def text_bot_base() -> str:
    return _env("TEXT_BOT_BASE", "http://127.0.0.1:8011").rstrip("/")


def mailer_base() -> str:
    return _env("MAILER_BASE", "http://127.0.0.1:8000").rstrip("/")


def _http(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    hdrs = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        hdrs.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            if not raw:
                return {"ok": True, "http_status": resp.status}
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": True, "http_status": resp.status, "raw": raw[:4000]}
            if isinstance(parsed, dict):
                parsed.setdefault("ok", True)
                parsed.setdefault("http_status", resp.status)
                return parsed
            return {"ok": True, "http_status": resp.status, "data": parsed}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except Exception:
            parsed = {"detail": detail[:2000]}
        return {"ok": False, "http_status": exc.code, "error": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def console_headers() -> dict[str, str]:
    token = _env("CONSOLE_TOKEN")
    headers: dict[str, str] = {}
    if token:
        headers["X-Console-Token"] = token
        headers["Authorization"] = f"Bearer {token}"
    return headers


def webhook_headers(*, also_outreach: bool = False) -> dict[str, str]:
    """Headers for office webhooks.

    Outreach UI auth accepts only ``OUTREACH_UI_TOKEN``. Prefer it (then
    ``OUTREACH_TOKEN``) over the shared ``WEBHOOK_TOKEN``, which is a different
    secret on prod and otherwise causes 401 on dashboard/packs/settings.
    """
    if also_outreach:
        token = (
            _env("OUTREACH_UI_TOKEN")
            or _env("OUTREACH_TOKEN")
            or _env("WEBHOOK_TOKEN")
        )
    else:
        token = (
            _env("WEBHOOK_TOKEN")
            or _env("OUTREACH_TOKEN")
            or _env("OUTREACH_UI_TOKEN")
        )
    headers: dict[str, str] = {}
    if token:
        headers["X-Webhook-Token"] = token
        if also_outreach:
            headers["X-Outreach-Token"] = token
        headers["Authorization"] = f"Bearer {token}"
    return headers


def brain_headers() -> dict[str, str]:
    headers = {
        "X-Principal-Id": _env("BRAIN_MCP_PRINCIPAL", "service:cursor-admin"),
        "X-Tenant-Id": _env("BRAIN_TENANT_ID", _env("BRAIN_MCP_TENANT", "quantum-labs")),
    }
    user = _env("BRAIN_MCP_USER_ID")
    if user:
        headers["X-User-Id"] = user
    admin = _env("BRAIN_MCP_ADMIN", "true").lower()
    if admin in ("1", "true", "yes"):
        headers["X-Admin"] = "true"
        headers.setdefault("X-User-Id", "office-mcp")
    groups = _env("BRAIN_MCP_GROUPS")
    if groups:
        headers["X-Groups"] = groups
    return headers


def _with_query(path: str, query: dict[str, Any] | None) -> str:
    if not query:
        return path
    cleaned = {k: v for k, v in query.items() if v is not None and v != ""}
    if not cleaned:
        return path
    return f"{path}?{urllib.parse.urlencode(cleaned)}"


def console_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    query: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{console_base()}{_with_query(path, query)}",
        headers=console_headers(),
        body=body,
        timeout=timeout,
    )


def campaign_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    query: dict[str, Any] | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{campaign_base()}{_with_query(path, query)}",
        headers=webhook_headers(),
        body=body,
        timeout=timeout,
    )


def knowledge_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 120.0,
    use_brain_headers: bool = True,
) -> dict[str, Any]:
    headers = brain_headers() if use_brain_headers else webhook_headers()
    # Legacy /api/knowledge/* uses webhook token; brain uses principal headers.
    if path.startswith("/api/knowledge"):
        headers = webhook_headers()
    # Brain hybrid search is heavier — default 120s (was 60, timed out for MCP).
    if path.startswith("/api/brain") and timeout < 120.0:
        timeout = 120.0
    return _http(
        method,
        f"{knowledge_base()}{path}",
        headers=headers,
        body=body,
        timeout=timeout,
    )


def calendar_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{calendar_base()}{path}",
        headers=webhook_headers(),
        body=body,
        timeout=timeout,
    )


def outreach_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    query: dict[str, Any] | None = None,
    timeout: float = 90.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{outreach_base()}{_with_query(path, query)}",
        headers=webhook_headers(also_outreach=True),
        body=body,
        timeout=timeout,
    )



def conference_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{conference_base()}{path}",
        headers=webhook_headers(),
        body=body,
        timeout=timeout,
    )


def files_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{files_base()}{path}",
        headers=webhook_headers(),
        body=body,
        timeout=timeout,
    )


def text_bot_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 90.0,
) -> dict[str, Any]:
    return _http(
        method,
        f"{text_bot_base()}{path}",
        headers=webhook_headers(),
        body=body,
        timeout=timeout,
    )


def health_probe(url: str, *, timeout: float = 5.0) -> dict[str, Any]:
    return _http("GET", url.rstrip("/") + "/health", timeout=timeout)
