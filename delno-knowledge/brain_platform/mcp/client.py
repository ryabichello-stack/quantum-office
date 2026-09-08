"""HTTP client helpers for MCP → Second Brain API."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def brain_base() -> str:
    return (
        os.getenv("AVA_KNOWLEDGE_BASE")
        or os.getenv("KNOWLEDGE_BASE")
        or "http://127.0.0.1:8017"
    ).rstrip("/")


def _headers() -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "X-Principal-Id": (
            os.getenv("BRAIN_MCP_PRINCIPAL") or "service:cursor-admin"
        ).strip(),
        "X-Tenant-Id": (
            os.getenv("BRAIN_TENANT_ID") or os.getenv("BRAIN_MCP_TENANT") or "quantum-labs"
        ).strip(),
    }
    user = (os.getenv("BRAIN_MCP_USER_ID") or "").strip()
    if user:
        headers["X-User-Id"] = user
    admin = (os.getenv("BRAIN_MCP_ADMIN") or "true").strip().lower()
    if admin in ("1", "true", "yes"):
        headers["X-Admin"] = "true"
        if "X-User-Id" not in headers:
            headers["X-User-Id"] = "cursor-mcp"
    groups = (os.getenv("BRAIN_MCP_GROUPS") or "").strip()
    if groups:
        headers["X-Groups"] = groups
    return headers


def brain_request(
    method: str,
    path: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 60.0,
) -> dict[str, Any]:
    url = f"{brain_base()}{path}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {"ok": True}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(detail)
        except Exception:
            parsed = {"detail": detail}
        return {"ok": False, "http_status": exc.code, "error": parsed}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}
