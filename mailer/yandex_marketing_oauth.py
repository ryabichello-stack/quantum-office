"""Yandex OAuth for Metrika / Direct / Webmaster (marketing app, separate from Telemost)."""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_SCOPE = "metrika:read metrika:write"

YANDEX_OAUTH_CLIENT_ID = os.getenv("YANDEX_MARKETING_OAUTH_CLIENT_ID", "").strip()
YANDEX_OAUTH_CLIENT_SECRET = os.getenv("YANDEX_MARKETING_OAUTH_CLIENT_SECRET", "").strip()
YANDEX_OAUTH_REDIRECT_URI = os.getenv(
    "YANDEX_MARKETING_OAUTH_REDIRECT_URI",
    "https://oauth.yandex.ru/verification_code",
).strip()
YANDEX_OAUTH_SCOPE = os.getenv("YANDEX_MARKETING_OAUTH_SCOPE", DEFAULT_SCOPE).strip() or DEFAULT_SCOPE
YANDEX_OAUTH_TOKEN_FILE = os.getenv(
    "YANDEX_MARKETING_OAUTH_TOKEN_FILE",
    "/opt/ava-mailer/yandex_marketing_oauth_tokens.json",
).strip()

YANDEX_OAUTH_AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
YANDEX_OAUTH_TOKEN_URL = "https://oauth.yandex.ru/token"


def oauth_configured() -> bool:
    return bool(YANDEX_OAUTH_CLIENT_ID and YANDEX_OAUTH_CLIENT_SECRET)


def _load_tokens() -> Dict[str, Any]:
    if not YANDEX_OAUTH_TOKEN_FILE or not os.path.isfile(YANDEX_OAUTH_TOKEN_FILE):
        return {}
    try:
        with open(YANDEX_OAUTH_TOKEN_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        logger.exception("Failed to read marketing token file")
        return {}


def _save_tokens(data: Dict[str, Any]) -> None:
    data["updated_at"] = int(time.time())
    with open(YANDEX_OAUTH_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(YANDEX_OAUTH_TOKEN_FILE, 0o600)
    except OSError:
        pass


def _token_request(payload: Dict[str, str]) -> Dict[str, Any]:
    body = urllib.parse.urlencode(payload).encode("utf-8")
    req = urllib.request.Request(
        YANDEX_OAUTH_TOKEN_URL,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _apply_token_response(data: Dict[str, Any], resp: Dict[str, Any]) -> Dict[str, Any]:
    access = resp.get("access_token")
    if access:
        data["access_token"] = access
    if resp.get("refresh_token"):
        data["refresh_token"] = resp["refresh_token"]
    if resp.get("token_type"):
        data["token_type"] = resp["token_type"]
    expires_in = resp.get("expires_in")
    if expires_in is not None:
        try:
            data["expires_at"] = int(time.time()) + int(expires_in) - 60
        except (TypeError, ValueError):
            pass
    return data


def _refresh_access_token(data: Dict[str, Any]) -> Optional[str]:
    refresh = data.get("refresh_token")
    if not refresh or not oauth_configured():
        return None
    try:
        resp = _token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": refresh,
                "client_id": YANDEX_OAUTH_CLIENT_ID,
                "client_secret": YANDEX_OAUTH_CLIENT_SECRET,
            }
        )
        data = _apply_token_response(data, resp)
        _save_tokens(data)
        return data.get("access_token")
    except urllib.error.HTTPError as exc:
        logger.error(
            "Yandex marketing token refresh failed: %s %s",
            exc.code,
            exc.read().decode("utf-8", errors="replace")[:300],
        )
    except Exception:
        logger.exception("Yandex marketing token refresh error")
    return None


def get_access_token() -> Optional[str]:
    data = _load_tokens()
    token = data.get("access_token")
    expires_at = data.get("expires_at")
    if token and expires_at and int(expires_at) > int(time.time()):
        return token
    if token and not expires_at:
        return token
    return _refresh_access_token(data) or data.get("access_token")


def oauth_status() -> Dict[str, Any]:
    data = _load_tokens()
    return {
        "configured": oauth_configured(),
        "has_refresh_token": bool(data.get("refresh_token")),
        "has_access_token": bool(data.get("access_token")),
        "expires_at": data.get("expires_at"),
        "token_file": YANDEX_OAUTH_TOKEN_FILE,
        "scope": YANDEX_OAUTH_SCOPE,
    }


def build_authorize_url() -> str:
    params = {
        "response_type": "code",
        "client_id": YANDEX_OAUTH_CLIENT_ID,
        "redirect_uri": YANDEX_OAUTH_REDIRECT_URI,
        "scope": YANDEX_OAUTH_SCOPE,
    }
    return f"{YANDEX_OAUTH_AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_authorization_code(code: str) -> Dict[str, Any]:
    if not code.strip():
        return {"ok": False, "error": "empty_code"}
    if not oauth_configured():
        return {"ok": False, "error": "oauth_not_configured"}
    try:
        resp = _token_request(
            {
                "grant_type": "authorization_code",
                "code": code.strip(),
                "client_id": YANDEX_OAUTH_CLIENT_ID,
                "client_secret": YANDEX_OAUTH_CLIENT_SECRET,
                "redirect_uri": YANDEX_OAUTH_REDIRECT_URI,
            }
        )
        data = _apply_token_response(_load_tokens(), resp)
        _save_tokens(data)
        return {"ok": True, "expires_at": data.get("expires_at")}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.error("Marketing OAuth code exchange failed: %s %s", exc.code, body[:500])
        return {"ok": False, "error": f"http_{exc.code}", "detail": body[:200]}
    except Exception as exc:
        logger.exception("Marketing OAuth code exchange error")
        return {"ok": False, "error": str(exc)}
