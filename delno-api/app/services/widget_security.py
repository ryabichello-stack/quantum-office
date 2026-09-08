"""Widget security helpers — rate limit + visitor binding (Commit 2)."""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.services.rate_limit import check_widget_rate_limit


def client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def enforce_widget_rate_limit(request: Request, *, site_key: str, action: str) -> None:
    ip = client_ip_from_request(request)
    result = check_widget_rate_limit(site_key=site_key, client_ip=ip, action=action)
    if result.allowed:
        return
    retry = int(result.retry_after_sec or 60)
    raise HTTPException(
        status_code=429,
        detail="rate_limit_exceeded",
        headers={"Retry-After": str(retry)},
    )
