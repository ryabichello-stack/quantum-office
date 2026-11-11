"""Multi-provider conference backends — tools-first.

Providers:
  yandex / telemost — Yandex Telemost (existing)
  google_meet       — Google Meet via Calendar API conferenceData
  zoom              — Zoom Meetings API
  teams             — Microsoft Teams onlineMeeting (Graph)
  jitsi             — public/self-hosted Jitsi room URL (no OAuth)

Without credentials: deterministic stub join URLs.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional, Protocol

import telemost as telemost_mod
import yandex_oauth

logger = logging.getLogger(__name__)

PROVIDER_NAMES = ("yandex", "google_meet", "zoom", "teams", "jitsi")
DEFAULT_PROVIDER = (
    os.getenv("CONFERENCE_DEFAULT_PROVIDER", "").strip().lower()
    or "yandex"
)

GOOGLE_MEET_TOKEN = (
    os.getenv("GOOGLE_MEET_TOKEN", "").strip()
    or os.getenv("GOOGLE_CALENDAR_TOKEN", "").strip()
    or os.getenv("GOOGLE_DRIVE_TOKEN", "").strip()
)
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
GOOGLE_MEET_CALENDAR_ID = os.getenv("GOOGLE_MEET_CALENDAR_ID", "primary").strip() or "primary"

ZOOM_ACCOUNT_ID = os.getenv("ZOOM_ACCOUNT_ID", "").strip()
ZOOM_CLIENT_ID = os.getenv("ZOOM_CLIENT_ID", "").strip()
ZOOM_CLIENT_SECRET = os.getenv("ZOOM_CLIENT_SECRET", "").strip()
ZOOM_ACCESS_TOKEN = os.getenv("ZOOM_ACCESS_TOKEN", "").strip()  # optional pre-minted

TEAMS_TOKEN = (
    os.getenv("TEAMS_TOKEN", "").strip()
    or os.getenv("MICROSOFT_GRAPH_TOKEN", "").strip()
    or os.getenv("OUTLOOK_CALENDAR_TOKEN", "").strip()
)
GRAPH_API = "https://graph.microsoft.com/v1.0"

JITSI_BASE_URL = (
    os.getenv("JITSI_BASE_URL", "").strip()
    or "https://meet.jit.si"
).rstrip("/")
# Jitsi is usable without tenant credentials (public room); mark configured always
# unless explicitly disabled.
JITSI_ENABLED = os.getenv("JITSI_ENABLED", "true").lower() in ("1", "true", "yes", "on")

STUB_WHEN_UNAUTH = os.getenv("CONFERENCE_STUB_WHEN_UNAUTH", "true").lower() in (
    "1",
    "true",
    "yes",
    "on",
)


class ConferenceProvider(Protocol):
    name: str

    def configured(self) -> bool: ...

    def create(
        self,
        *,
        title: str,
        waiting_room_level: Optional[str] = None,
    ) -> dict[str, Any]: ...


def _slug(title: str) -> str:
    raw = re.sub(r"[^a-zA-Z0-9]+", "-", (title or "meet").strip())[:40].strip("-")
    return raw or "meet"


def _stub(provider: str, title: str) -> dict[str, Any]:
    slug = _slug(title)
    return {
        "ok": True,
        "stub": True,
        "provider": provider,
        "conference_id": f"stub-{provider}-{slug}",
        "join_url": f"https://stub.{provider}.delno.local/{slug}",
        "error": None,
        "message": f"Stub {provider} conference (credentials not configured)",
    }


def _http_json(
    url: str,
    *,
    headers: dict[str, str],
    method: str = "GET",
    data: bytes | None = None,
    timeout: float = 30.0,
) -> dict:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"http_{exc.code}:{body}") from exc


class YandexProvider:
    name = "yandex"

    def configured(self) -> bool:
        if not telemost_mod.TELEMOST_ENABLED:
            return False
        status = yandex_oauth.oauth_status()
        return bool(status.get("has_access_token") or status.get("static_token_set"))

    def create(self, *, title: str, waiting_room_level: Optional[str] = None) -> dict[str, Any]:
        conf_id, join_url, err = telemost_mod.create_conference(
            title=title,
            waiting_room_level=waiting_room_level,
        )
        if not join_url:
            if STUB_WHEN_UNAUTH:
                out = _stub(self.name, title)
                out["error"] = err
                return out
            return {
                "ok": False,
                "stub": False,
                "provider": self.name,
                "conference_id": "",
                "join_url": "",
                "error": err or "telemost_create_failed",
                "message": "Не удалось создать конференцию в Яндекс Телемост",
            }
        stub = str(conf_id or "").startswith("stub-") or "stub.telemost.delno.local" in join_url
        return {
            "ok": True,
            "stub": stub,
            "provider": self.name,
            "conference_id": conf_id or "",
            "join_url": join_url,
            "error": None,
            "message": ("Stub Telemost" if stub else "Telemost created") + f": {join_url}",
        }


class GoogleMeetProvider:
    name = "google_meet"

    def configured(self) -> bool:
        return bool(GOOGLE_MEET_TOKEN)

    def create(self, *, title: str, waiting_room_level: Optional[str] = None) -> dict[str, Any]:
        if not self.configured():
            return _stub(self.name, title) if STUB_WHEN_UNAUTH else {
                "ok": False,
                "provider": self.name,
                "error": "google_meet_not_configured",
                "join_url": "",
                "conference_id": "",
                "message": "Set GOOGLE_MEET_TOKEN / GOOGLE_CALENDAR_TOKEN",
            }
        # Create a short calendar event with Meet conferenceData
        cal_id = urllib.parse.quote(GOOGLE_MEET_CALENDAR_ID, safe="@")
        payload = {
            "summary": title or "Meeting",
            "conferenceData": {
                "createRequest": {
                    "requestId": secrets.token_hex(8),
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                }
            },
        }
        url = (
            f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events"
            f"?conferenceDataVersion=1"
        )
        headers = {
            "Authorization": f"Bearer {GOOGLE_MEET_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        try:
            meta = _http_json(
                url,
                headers=headers,
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
            )
        except Exception as exc:
            logger.exception("[GOOGLE_MEET] %s", exc)
            return {
                "ok": False,
                "provider": self.name,
                "error": "google_meet_error",
                "join_url": "",
                "conference_id": "",
                "message": str(exc)[:300],
            }
        entry_points = ((meta.get("conferenceData") or {}).get("entryPoints")) or []
        join = ""
        for ep in entry_points:
            if ep.get("entryPointType") == "video" and ep.get("uri"):
                join = str(ep["uri"])
                break
        if not join:
            join = str(meta.get("hangoutLink") or "")
        return {
            "ok": bool(join),
            "stub": False,
            "provider": self.name,
            "conference_id": str((meta.get("conferenceData") or {}).get("conferenceId") or meta.get("id") or ""),
            "join_url": join,
            "error": None if join else "missing_join_url",
            "message": f"Google Meet: {join}" if join else "Meet link missing in API response",
            "html_link": meta.get("htmlLink"),
        }


def _zoom_token() -> str:
    if ZOOM_ACCESS_TOKEN:
        return ZOOM_ACCESS_TOKEN
    if not (ZOOM_ACCOUNT_ID and ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET):
        return ""
    # Server-to-Server OAuth
    import base64

    auth = base64.b64encode(f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}".encode()).decode()
    data = urllib.parse.urlencode(
        {"grant_type": "account_credentials", "account_id": ZOOM_ACCOUNT_ID}
    ).encode()
    try:
        meta = _http_json(
            "https://zoom.us/oauth/token",
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
            data=data,
        )
        return str(meta.get("access_token") or "")
    except Exception as exc:
        logger.warning("[ZOOM] token error: %s", exc)
        return ""


class ZoomProvider:
    name = "zoom"

    def configured(self) -> bool:
        return bool(ZOOM_ACCESS_TOKEN or (ZOOM_ACCOUNT_ID and ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET))

    def create(self, *, title: str, waiting_room_level: Optional[str] = None) -> dict[str, Any]:
        if not self.configured():
            return _stub(self.name, title) if STUB_WHEN_UNAUTH else {
                "ok": False,
                "provider": self.name,
                "error": "zoom_not_configured",
                "join_url": "",
                "conference_id": "",
                "message": "Set ZOOM_ACCESS_TOKEN or ZOOM_ACCOUNT_ID/CLIENT_ID/SECRET",
            }
        token = _zoom_token()
        if not token:
            return {
                "ok": False,
                "provider": self.name,
                "error": "zoom_token_failed",
                "join_url": "",
                "conference_id": "",
                "message": "Could not mint Zoom access token",
            }
        payload = {
            "topic": title or "Meeting",
            "type": 1,  # instant
            "settings": {"waiting_room": True},
        }
        try:
            meta = _http_json(
                "https://api.zoom.us/v2/users/me/meetings",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
            )
        except Exception as exc:
            logger.exception("[ZOOM] %s", exc)
            return {
                "ok": False,
                "provider": self.name,
                "error": "zoom_error",
                "join_url": "",
                "conference_id": "",
                "message": str(exc)[:300],
            }
        join = str(meta.get("join_url") or "")
        return {
            "ok": bool(join),
            "stub": False,
            "provider": self.name,
            "conference_id": str(meta.get("id") or ""),
            "join_url": join,
            "error": None if join else "missing_join_url",
            "message": f"Zoom: {join}" if join else "Zoom join_url missing",
            "password": meta.get("password"),
        }


class TeamsProvider:
    name = "teams"

    def configured(self) -> bool:
        return bool(TEAMS_TOKEN)

    def create(self, *, title: str, waiting_room_level: Optional[str] = None) -> dict[str, Any]:
        if not self.configured():
            return _stub(self.name, title) if STUB_WHEN_UNAUTH else {
                "ok": False,
                "provider": self.name,
                "error": "teams_not_configured",
                "join_url": "",
                "conference_id": "",
                "message": "Set TEAMS_TOKEN / MICROSOFT_GRAPH_TOKEN",
            }
        payload = {"subject": title or "Meeting"}
        try:
            meta = _http_json(
                f"{GRAPH_API}/me/onlineMeetings",
                headers={
                    "Authorization": f"Bearer {TEAMS_TOKEN}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
                data=json.dumps(payload).encode("utf-8"),
            )
        except Exception as exc:
            logger.exception("[TEAMS] %s", exc)
            return {
                "ok": False,
                "provider": self.name,
                "error": "teams_error",
                "join_url": "",
                "conference_id": "",
                "message": str(exc)[:300],
            }
        join = str(meta.get("joinWebUrl") or meta.get("joinUrl") or "")
        return {
            "ok": bool(join),
            "stub": False,
            "provider": self.name,
            "conference_id": str(meta.get("id") or ""),
            "join_url": join,
            "error": None if join else "missing_join_url",
            "message": f"Teams: {join}" if join else "Teams join URL missing",
        }


class JitsiProvider:
    name = "jitsi"

    def configured(self) -> bool:
        return JITSI_ENABLED and bool(JITSI_BASE_URL)

    def create(self, *, title: str, waiting_room_level: Optional[str] = None) -> dict[str, Any]:
        if not self.configured():
            return _stub(self.name, title)
        room = f"{_slug(title)}-{secrets.token_hex(3)}"
        join = f"{JITSI_BASE_URL}/{room}"
        return {
            "ok": True,
            "stub": False,
            "provider": self.name,
            "conference_id": room,
            "join_url": join,
            "error": None,
            "message": f"Jitsi room: {join}",
        }


_REGISTRY: dict[str, ConferenceProvider] = {
    "yandex": YandexProvider(),
    "telemost": YandexProvider(),  # alias object same class instance? separate for clarity
    "google_meet": GoogleMeetProvider(),
    "zoom": ZoomProvider(),
    "teams": TeamsProvider(),
    "jitsi": JitsiProvider(),
}
# ensure telemost alias shares behavior
_REGISTRY["telemost"] = _REGISTRY["yandex"]

_ALIASES = {
    "ya": "yandex",
    "telemost": "yandex",
    "yandex_telemost": "yandex",
    "meet": "google_meet",
    "google": "google_meet",
    "gmeet": "google_meet",
    "ms_teams": "teams",
    "msteams": "teams",
    "microsoft_teams": "teams",
}


def normalize_provider(provider: Optional[str]) -> str:
    raw = (provider or DEFAULT_PROVIDER or "yandex").strip().lower()
    raw = _ALIASES.get(raw, raw)
    if raw not in ("yandex", "google_meet", "zoom", "teams", "jitsi"):
        raise ValueError(f"unknown conference provider: {provider}")
    return raw


def get_provider(provider: Optional[str] = None) -> ConferenceProvider:
    return _REGISTRY[normalize_provider(provider)]


def list_providers() -> list[dict[str, Any]]:
    items = []
    default = normalize_provider(DEFAULT_PROVIDER)
    for name in PROVIDER_NAMES:
        p = _REGISTRY[name]
        items.append(
            {
                "provider": name,
                "configured": p.configured(),
                "default": name == default,
            }
        )
    return items


def providers_status() -> dict[str, Any]:
    return {
        "default_provider": normalize_provider(DEFAULT_PROVIDER),
        "providers": list_providers(),
        "creds_policy": "tools_first",
        "stub_when_unauth": STUB_WHEN_UNAUTH,
    }
