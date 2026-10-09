"""Yandex Wordstat API (marketing OAuth + ClientId)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List

from yandex_marketing_oauth import get_access_token, oauth_configured

logger = logging.getLogger(__name__)

API_BASE = "https://api.wordstat.yandex.net"
CLIENT_ID = os.getenv("YANDEX_MARKETING_OAUTH_CLIENT_ID", "").strip()


def _post(path: str, body: Dict[str, Any]) -> Dict[str, Any]:
    token = get_access_token()
    if not token:
        return {"ok": False, "error": "no_access_token"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json;charset=utf-8",
        "Accept-Language": "ru",
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}{path}", data=data, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        logger.error("Wordstat API %s: %s %s", path, exc.code, err_body[:400])
        return {"ok": False, "error": f"http_{exc.code}", "detail": err_body[:500]}
    except Exception as exc:
        logger.exception("Wordstat API error")
        return {"ok": False, "error": str(exc)}


def top_requests_for_phrase(phrase: str, num_phrases: int = 40) -> Dict[str, Any]:
    if not oauth_configured():
        return {"ok": False, "error": "marketing_oauth_not_configured"}
    phrase = phrase.strip()
    if not phrase:
        return {"ok": False, "error": "empty_phrase"}
    return _post(
        "/v1/topRequests",
        {
            "phrase": phrase,
            "numPhrases": min(max(num_phrases, 1), 2000),
            "regions": [225],
            "devices": ["all"],
        },
    )


def top_requests(phrases: List[str], num_phrases: int = 40) -> Dict[str, Any]:
    clean = [p.strip() for p in phrases if p.strip()]
    if not clean:
        return {"ok": False, "error": "empty_phrases"}
    by_phrase: Dict[str, Any] = {}
    errors: List[Dict[str, Any]] = []
    for phrase in clean[:8]:
        result = top_requests_for_phrase(phrase, num_phrases=num_phrases)
        if result.get("ok"):
            by_phrase[phrase] = result.get("data")
        else:
            errors.append({"phrase": phrase, **result})
    if not by_phrase:
        return {"ok": False, "error": "all_phrases_failed", "errors": errors}
    return {"ok": True, "data": {"by_phrase": by_phrase}, "errors": errors or None}


def seo_seed_phrases() -> Dict[str, Any]:
    seeds = [
        "ии сотрудник",
        "голосовой бот для бизнеса",
        "бот для записи клиентов",
        "автоматизация звонков",
        "чат бот для сайта",
    ]
    return top_requests(seeds)
