"""Resolve Principal from gateway headers / token claims. Tenant never from free-form body alone."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import Header, HTTPException

from brain_platform.security.acl import Principal, reject_client_supplied_tenant

DEFAULT_TENANT = os.getenv("BRAIN_TENANT_ID", "quantum-labs").strip() or "quantum-labs"


def principal_from_headers(
    *,
    x_principal_id: Optional[str] = None,
    x_tenant_id: Optional[str] = None,
    x_groups: Optional[str] = None,
    x_user_id: Optional[str] = None,
    x_admin: Optional[str] = None,
    body_tenant_id: Optional[str] = None,
) -> Principal:
    principal_id = (x_principal_id or "").strip()
    if not principal_id:
        # Fail closed for brain API — unknown = deny via empty principal that maps to deny
        principal_id = "service:unknown"

    claims = {"tenant_id": (x_tenant_id or "").strip() or DEFAULT_TENANT}
    body = {}
    if body_tenant_id is not None:
        body["tenant_id"] = body_tenant_id
    try:
        tenant_id = reject_client_supplied_tenant(body, claims)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    groups = tuple(
        g.strip()
        for g in (x_groups or "").split(",")
        if g.strip()
    )
    is_admin = (x_admin or "").strip().lower() in ("1", "true", "yes")
    return Principal(
        principal_id=principal_id,
        tenant_id=tenant_id,
        groups=groups,
        user_id=(x_user_id or "").strip() or None,
        is_admin=is_admin,
    )


def require_brain_enabled() -> None:
    if os.getenv("BRAIN_ENABLED", "true").lower() in ("0", "false", "no", "off"):
        raise HTTPException(status_code=503, detail="brain_disabled")
