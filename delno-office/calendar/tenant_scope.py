"""Per-request calendar credentials. Env tokens are not the default.

A bound request uses only the credentials dict from the caller (delno-api
tenant vault). Server env is consulted when that caller sets
``allow_env_fallback`` — reserved for an explicitly marked service tenant.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

_SCOPE: ContextVar[dict[str, Any] | None] = ContextVar("calendar_request_scope", default=None)


def request_bound() -> bool:
    return _SCOPE.get() is not None


def request_credentials() -> dict[str, Any]:
    scope = _SCOPE.get() or {}
    raw = scope.get("credentials")
    return raw if isinstance(raw, dict) else {}


def allow_env_fallback() -> bool:
    scope = _SCOPE.get() or {}
    if scope.get("allow_env_fallback"):
        return True
    return bool(request_credentials().get("allow_env_fallback"))


def request_tenant_id() -> str:
    scope = _SCOPE.get() or {}
    return str(scope.get("tenant_id") or "").strip()


@contextmanager
def bind_request(
    *,
    tenant_id: str,
    credentials: dict[str, Any] | None = None,
    allow_env_fallback: bool = False,
) -> Iterator[None]:
    payload = {
        "tenant_id": (tenant_id or "").strip(),
        "credentials": dict(credentials or {}),
        "allow_env_fallback": bool(allow_env_fallback),
    }
    token = _SCOPE.set(payload)
    try:
        yield
    finally:
        _SCOPE.reset(token)
