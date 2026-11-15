"""Reject file-broker calls that are not pinned to one tenant.

The broker does not own the tenant directory. delno-api sends the tenant id
it already authenticated. A missing id, or a body id that disagrees with
``X-Tenant-Id``, is refused before any cloud token is read.
"""

from __future__ import annotations

from fastapi import HTTPException


def require_tenant(body_tenant: str | None, header_tenant: str | None) -> str:
    body = (body_tenant or "").strip()
    header = (header_tenant or "").strip()
    if not body and not header:
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_required", "message": "Запрос без тенанта отклонён"},
        )
    if body and header and body != header:
        raise HTTPException(
            status_code=403,
            detail={"error": "tenant_mismatch", "message": "Чужой тенант отклонён"},
        )
    return body or header
