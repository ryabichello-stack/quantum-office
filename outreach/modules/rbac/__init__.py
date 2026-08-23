"""RBAC for Outreach API — roles on top of existing UI token auth.

Default: RBAC off → authenticated callers act as ``owner``.
Enable with ``OUTREACH_RBAC_ENABLED=1`` and optional secondary tokens:

  OUTREACH_ROLE_TOKENS=ops:<token>,analyst:<token>,viewer:<token>

Primary ``OUTREACH_UI_TOKEN`` maps to ``OUTREACH_UI_ROLE`` (default owner).
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import HTTPException, Request

# Permission catalog (string ids — stable for UI / tests)
PERM_READ = "read"
PERM_SEND = "outreach.send"
PERM_SETTINGS = "outreach.settings"
PERM_ACCOUNTS_WRITE = "accounts.write"
PERM_SOCIAL_WRITE = "social.write"
PERM_STUDIO_WRITE = "studio.write"
PERM_ADMIN = "admin"
PERM_USAGE = "usage.read"

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            PERM_READ,
            PERM_SEND,
            PERM_SETTINGS,
            PERM_ACCOUNTS_WRITE,
            PERM_SOCIAL_WRITE,
            PERM_STUDIO_WRITE,
            PERM_ADMIN,
            PERM_USAGE,
        }
    ),
    "ops": frozenset(
        {
            PERM_READ,
            PERM_SEND,
            PERM_ACCOUNTS_WRITE,
            PERM_SOCIAL_WRITE,
            PERM_STUDIO_WRITE,
            PERM_USAGE,
        }
    ),
    "analyst": frozenset({PERM_READ, PERM_USAGE}),
    "viewer": frozenset({PERM_READ}),
}

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# First match wins. Write/mutate paths only (GET always allowed with PERM_READ).
_WRITE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^/api/v1/tenants/bootstrap"), PERM_ADMIN),
    (re.compile(r"^/api/settings$"), PERM_SETTINGS),
    (re.compile(r"^/api/brand/"), PERM_SETTINGS),
    (re.compile(r"^/api/packs/.+/presentation"), PERM_SETTINGS),
    (re.compile(r"^/(send-batch|send-one|dry-run|sync|check-replies)$"), PERM_SEND),
    (re.compile(r"^/api/outbox"), PERM_SEND),
    (re.compile(r"^/api/modules/clients/"), PERM_SEND),
    (re.compile(r"^/api/modules/social/"), PERM_SOCIAL_WRITE),
    (re.compile(r"^/api/modules/accounts/"), PERM_ACCOUNTS_WRITE),
    (re.compile(r"^/api/modules/orchestrator/"), PERM_SEND),
    (re.compile(r"^/api/modules/content_studio/"), PERM_STUDIO_WRITE),
    (re.compile(r"^/api/modules/radar/"), PERM_STUDIO_WRITE),
    (re.compile(r"^/api/modules/video_studio/"), PERM_STUDIO_WRITE),
    (re.compile(r"^/api/modules/social_publish/"), PERM_STUDIO_WRITE),
    (re.compile(r"^/api/ops/"), PERM_SEND),
    (re.compile(r"^/api/callback-cta/"), PERM_SETTINGS),
]


@dataclass(frozen=True)
class Principal:
    role: str
    token_label: str = "ui"

    def allows(self, permission: str) -> bool:
        perms = ROLE_PERMISSIONS.get(self.role) or frozenset()
        return permission in perms

    def to_dict(self) -> dict[str, Any]:
        perms = sorted(ROLE_PERMISSIONS.get(self.role) or [])
        return {
            "role": self.role,
            "token_label": self.token_label,
            "permissions": perms,
            "rbac_enabled": rbac_enabled(),
        }


def rbac_enabled() -> bool:
    return (os.getenv("OUTREACH_RBAC_ENABLED") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def parse_role_tokens() -> dict[str, str]:
    """Map raw token → role from OUTREACH_ROLE_TOKENS=role:token,..."""
    raw = (os.getenv("OUTREACH_ROLE_TOKENS") or "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in raw.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        role, token = part.split(":", 1)
        role = role.strip().lower()
        token = token.strip()
        if role in ROLE_PERMISSIONS and token:
            out[token] = role
    return out


def _parse_role_tokens() -> dict[str, str]:
    return parse_role_tokens()


def resolve_principal(token: str) -> Principal:
    """Map a validated-looking token to a Principal (caller must already auth-check)."""
    token = (token or "").strip()
    if not rbac_enabled():
        return Principal(role="owner", token_label="ui")

    primary = (os.getenv("OUTREACH_UI_TOKEN") or "").strip()
    primary_role = (os.getenv("OUTREACH_UI_ROLE") or "owner").strip().lower()
    if primary_role not in ROLE_PERMISSIONS:
        primary_role = "owner"

    if primary and token and secrets.compare_digest(token, primary):
        return Principal(role=primary_role, token_label="ui")

    for mapped_token, role in _parse_role_tokens().items():
        if secrets.compare_digest(token, mapped_token):
            return Principal(role=role, token_label=role)

    # Auth layer should have rejected unknown tokens; fallback viewer if somehow here
    return Principal(role="viewer", token_label="unknown")


def permission_for_request(method: str, path: str) -> str | None:
    """Return required permission for a mutating request, or None if only read."""
    if method.upper() in SAFE_METHODS:
        return None
    path = path.split("?")[0]
    for pattern, perm in _WRITE_RULES:
        if pattern.search(path):
            return perm
    # Default: mutating unknown paths need ops-level send (conservative)
    return PERM_SEND


def enforce_request(principal: Principal, method: str, path: str) -> None:
    if not principal.allows(PERM_READ):
        raise HTTPException(status_code=403, detail="Forbidden — missing read")
    needed = permission_for_request(method, path)
    if needed is None:
        return
    if not principal.allows(needed):
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden — role={principal.role} needs {needed}",
        )


def attach_principal(request: Request, token: str) -> Principal:
    principal = resolve_principal(token)
    request.state.principal = principal
    if rbac_enabled():
        enforce_request(principal, request.method, request.url.path)
    return principal


def require_permission(permission: str) -> Callable[..., Principal]:
    """FastAPI dependency factory for explicit permission checks on a route."""

    async def _dep(request: Request) -> Principal:
        principal = getattr(request.state, "principal", None)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        if not principal.allows(permission):
            raise HTTPException(
                status_code=403,
                detail=f"Forbidden — needs {permission}",
            )
        return principal

    return _dep


class RbacModule:
    """Catalog-only module (routes mounted from main for /api/v1/me)."""

    name = "rbac"
    version = "0.1.0"

    def init_db(self) -> None:
        return None

    def register_routes(self, router: Any) -> None:
        @router.get("/health")
        def health() -> dict[str, Any]:
            return self.health()

        @router.get("/roles")
        def roles() -> dict[str, Any]:
            return {
                "ok": True,
                "rbac_enabled": rbac_enabled(),
                "roles": {
                    name: sorted(perms) for name, perms in ROLE_PERMISSIONS.items()
                },
            }

    def on_startup(self, ctx: Any) -> None:
        return None

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "rbac_enabled": rbac_enabled(), "roles": list(ROLE_PERMISSIONS)}
