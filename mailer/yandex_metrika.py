"""Yandex Metrika Management API helpers."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from yandex_marketing_oauth import get_access_token, oauth_configured

logger = logging.getLogger(__name__)

API_BASE = "https://api-metrika.yandex.net"


def _normalize_site(site: str) -> str:
    s = (site or "").strip().lower()
    s = re.sub(r"^https?://", "", s)
    return s.rstrip("/")


def _request(method: str, path: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = get_access_token()
    if not token:
        return {"ok": False, "error": "no_access_token"}
    data = None
    headers = {"Authorization": f"OAuth {token}"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Metrika API %s %s: %s %s", method, path, exc.code, err_body[:400])
        return {"ok": False, "error": f"http_{exc.code}", "detail": err_body[:500]}
    except Exception as exc:
        logger.exception("Metrika API error")
        return {"ok": False, "error": str(exc)}


def list_counters() -> Dict[str, Any]:
    return _request("GET", "/management/v1/counters")


def _counter_sites(counter: Dict[str, Any]) -> List[str]:
    sites: List[str] = []
    site2 = counter.get("site2") or {}
    if isinstance(site2, dict) and site2.get("site"):
        sites.append(_normalize_site(str(site2["site"])))
    if counter.get("site"):
        sites.append(_normalize_site(str(counter["site"])))
    for u in counter.get("mirrors") or []:
        if isinstance(u, str):
            sites.append(_normalize_site(u))
    return sites


def find_counter_for_site(site: str) -> Optional[int]:
    want = _normalize_site(site)
    listed = list_counters()
    if not listed.get("ok"):
        return None
    for counter in listed.get("data", {}).get("counters") or []:
        if want in _counter_sites(counter):
            try:
                return int(counter["id"])
            except (TypeError, ValueError, KeyError):
                continue
    return None


def create_counter(site: str, name: str) -> Tuple[Optional[int], Dict[str, Any]]:
    body = {
        "counter": {
            "name": name,
            "type": "simple",
            "site2": {"site": _normalize_site(site)},
        }
    }
    result = _request("POST", "/management/v1/counters", body)
    if not result.get("ok"):
        return None, result
    counter = result.get("data", {}).get("counter") or {}
    try:
        return int(counter["id"]), result
    except (TypeError, ValueError, KeyError):
        return None, result


def ensure_counter(site: str, name: str = "DELNO — dlno.ru") -> Dict[str, Any]:
    if not oauth_configured():
        return {"ok": False, "error": "marketing_oauth_not_configured"}
    existing = find_counter_for_site(site)
    if existing:
        return {"ok": True, "counter_id": existing, "created": False, "site": _normalize_site(site)}
    counter_id, raw = create_counter(site, name)
    if counter_id:
        return {"ok": True, "counter_id": counter_id, "created": True, "site": _normalize_site(site)}
    return {"ok": False, "error": "create_failed", "detail": raw}
