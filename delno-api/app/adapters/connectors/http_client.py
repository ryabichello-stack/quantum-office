"""Shared HTTP helper for optional upstream office services."""

from __future__ import annotations

from typing import Any

import httpx


def post_json(
    base_url: str,
    path: str,
    *,
    json: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, Any] | None, str | None]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if token:
        headers["X-Webhook-Token"] = token
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(url, json=json or {}, headers=headers)
            try:
                body = response.json()
            except Exception:
                body = None
            if response.status_code >= 400:
                detail = ""
                if isinstance(body, dict):
                    detail = str(body.get("message") or body.get("detail") or body)[:300]
                else:
                    detail = (response.text or "")[:300]
                return response.status_code, body if isinstance(body, dict) else None, detail or "upstream_error"
            return response.status_code, body if isinstance(body, dict) else {}, None
    except httpx.HTTPError as exc:
        return 0, None, str(exc)[:300]


def get_json(
    base_url: str,
    path: str,
    *,
    token: str | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any] | None, str | None]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers: dict[str, str] = {}
    if token:
        headers["X-Webhook-Token"] = token
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url, headers=headers)
            try:
                body = response.json()
            except Exception:
                body = None
            if response.status_code >= 400:
                return response.status_code, body if isinstance(body, dict) else None, (response.text or "")[:300]
            return response.status_code, body if isinstance(body, dict) else {}, None
    except httpx.HTTPError as exc:
        return 0, None, str(exc)[:300]
