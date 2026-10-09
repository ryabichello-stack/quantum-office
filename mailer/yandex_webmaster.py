"""Yandex Webmaster API v4 (marketing OAuth token)."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from yandex_marketing_oauth import get_access_token, oauth_configured

logger = logging.getLogger(__name__)

API_BASE = "https://api.webmaster.yandex.net/v4"


def _request(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = get_access_token()
    if not token:
        return {"ok": False, "error": "no_access_token"}
    data = None
    headers = {"Authorization": f"OAuth {token}", "Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Webmaster API %s %s: %s %s", method, path, exc.code, err_body[:400])
        try:
            detail = json.loads(err_body) if err_body else {}
        except json.JSONDecodeError:
            detail = {"raw": err_body[:500]}
        return {"ok": False, "error": f"http_{exc.code}", "detail": detail}
    except Exception as exc:
        logger.exception("Webmaster API error")
        return {"ok": False, "error": str(exc)}


def get_user_id() -> Optional[int]:
    result = _request("GET", "/user")
    if not result.get("ok"):
        return None
    try:
        return int(result["data"]["user_id"])
    except (KeyError, TypeError, ValueError):
        return None


def list_hosts(user_id: int) -> Dict[str, Any]:
    return _request("GET", f"/user/{user_id}/hosts")


def add_host(user_id: int, host_url: str) -> Dict[str, Any]:
    return _request("POST", f"/user/{user_id}/hosts", {"host_url": host_url})


def add_sitemap(user_id: int, host_id: str, sitemap_url: str) -> Dict[str, Any]:
    path = f"/user/{user_id}/hosts/{host_id}/user-added-sitemaps"
    return _request("POST", path, {"url": sitemap_url})


def get_verification(user_id: int, host_id: str) -> Dict[str, Any]:
    return _request("GET", f"/user/{user_id}/hosts/{host_id}/verification")


def start_verification(user_id: int, host_id: str, verification_type: str = "META_TAG") -> Dict[str, Any]:
    path = f"/user/{user_id}/hosts/{host_id}/verification?verification_type={verification_type}"
    return _request("POST", path, {})


def seo_bootstrap(host_url: str = "https://dlno.ru/", sitemap_url: str = "https://dlno.ru/sitemap.xml") -> Dict[str, Any]:
    if not oauth_configured():
        return {"ok": False, "error": "marketing_oauth_not_configured"}
    user_id = get_user_id()
    if not user_id:
        return {"ok": False, "error": "webmaster_user_unavailable"}

    hosts_result = list_hosts(user_id)
    host_id = None
    verified = False
    if hosts_result.get("ok"):
        for host in hosts_result.get("data", {}).get("hosts") or []:
            if host_url.rstrip("/") in str(host.get("ascii_host_url", "")) or host_url in str(
                host.get("host_url", "")
            ):
                host_id = host.get("host_id")
                verified = bool(host.get("verified"))
                break

    added_host = None
    if not host_id:
        add_result = add_host(user_id, host_url)
        if add_result.get("ok"):
            host_id = add_result.get("data", {}).get("host_id")
            verified = bool(add_result.get("data", {}).get("verified"))
            added_host = True
        else:
            return {"ok": False, "step": "add_host", **add_result}

    verification = None
    if host_id:
        verification = get_verification(user_id, host_id)

    verify_start = None
    if host_id and not verified and verification and verification.get("ok"):
        verify_start = start_verification(user_id, host_id, "META_TAG")
        if verify_start.get("ok"):
            verification = get_verification(user_id, host_id)
            verified = str((verification.get("data") or {}).get("verification_state", "")).upper() in (
                "VERIFIED",
                "IN_PROGRESS",
            )

    sitemap = None
    if host_id and verified:
        sitemap = add_sitemap(user_id, host_id, sitemap_url)

    return {
        "ok": True,
        "user_id": user_id,
        "host_id": host_id,
        "verified": verified,
        "added_host": added_host,
        "verification": verification,
        "verification_start": verify_start,
        "sitemap_submit": sitemap,
        "note": "Пока сайт не verified, sitemap в Вебmaster не примут — добавьте meta/HTML из verification.",
    }
