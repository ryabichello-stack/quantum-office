"""Multi-provider calendar backends — tools-first.

Sources:
  mailru   — Mail.ru CalDAV (existing)
  yandex   — Yandex Calendar CalDAV
  google   — Google Calendar API
  outlook  — Microsoft Graph calendar

Without credentials each provider returns stub slots / staged creates.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Optional, Protocol

import caldav
import pytz

import caldav_client as shared

logger = logging.getLogger(__name__)

PROVIDER_NAMES = ("mailru", "yandex", "google", "outlook")
DEFAULT_SOURCE = (
    os.getenv("CALENDAR_DEFAULT_SOURCE", "").strip().lower()
    or "mailru"
)

# Yandex CalDAV
YANDEX_CALDAV_URL = os.getenv("YANDEX_CALDAV_URL", "https://caldav.yandex.ru").strip()
YANDEX_CALDAV_USERNAME = os.getenv("YANDEX_CALDAV_USERNAME", "").strip()
YANDEX_CALDAV_PASSWORD = os.getenv("YANDEX_CALDAV_PASSWORD", "").strip()
YANDEX_CALENDAR_URL = os.getenv("YANDEX_CALENDAR_URL", "").strip()

# Google Calendar
GOOGLE_CALENDAR_TOKEN = (
    os.getenv("GOOGLE_CALENDAR_TOKEN", "").strip()
    or os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "").strip()
)
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"

# Outlook / Microsoft Graph
OUTLOOK_CALENDAR_TOKEN = (
    os.getenv("OUTLOOK_CALENDAR_TOKEN", "").strip()
    or os.getenv("MICROSOFT_GRAPH_TOKEN", "").strip()
    or os.getenv("ONEDRIVE_TOKEN", "").strip()
)
OUTLOOK_CALENDAR_ID = os.getenv("OUTLOOK_CALENDAR_ID", "").strip()  # empty = default calendar
GRAPH_API = "https://graph.microsoft.com/v1.0"


class CalendarProvider(Protocol):
    name: str

    def configured(self) -> bool: ...

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool: ...

    def suggest_slots(
        self,
        desired_start: datetime,
        *,
        duration_min: int = 30,
        suggestions_count: int = 3,
        search_hours_ahead: int = 72,
    ) -> list[dict]: ...

    def create_event(
        self,
        *,
        start_dt: datetime,
        end_dt: datetime,
        summary: str,
        description: str = "",
        location: str = "",
        attendee_email: str = "",
        event_url: str = "",
    ) -> dict[str, Any]: ...


def _stub_suggestions(
    desired_start: datetime,
    *,
    duration_min: int,
    suggestions_count: int,
    search_hours_ahead: int,
    source: str,
) -> list[dict]:
    suggestions: list[dict] = []
    current = desired_start
    end_limit = desired_start + timedelta(hours=search_hours_ahead)
    duration = timedelta(minutes=duration_min)
    while current + duration <= end_limit and len(suggestions) < suggestions_count:
        candidate_end = current + duration
        suggestions.append(
            {
                "start": current.isoformat(),
                "end": candidate_end.isoformat(),
                "label": shared.format_slot(current) + f" (stub:{source})",
                "duration_min": duration_min,
                "stub": True,
                "source": source,
            }
        )
        current += timedelta(minutes=30)
    return suggestions


def _stub_create(
    *,
    source: str,
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
) -> dict[str, Any]:
    return {
        "ok": True,
        "created": False,
        "stub": True,
        "dry_run": True,
        "source": source,
        "summary": summary,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
        "message": f"{source} credentials not configured — meeting staged (tools-first)",
    }


class MailruProvider:
    name = "mailru"

    def configured(self) -> bool:
        return shared.credentials_configured()

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        return shared.slot_is_free(start_dt, end_dt)

    def suggest_slots(
        self,
        desired_start: datetime,
        *,
        duration_min: int = 30,
        suggestions_count: int = 3,
        search_hours_ahead: int = 72,
    ) -> list[dict]:
        items = shared.suggest_slots(
            desired_start,
            duration_min=duration_min,
            suggestions_count=suggestions_count,
            search_hours_ahead=search_hours_ahead,
        )
        for item in items:
            item["source"] = self.name
        return items

    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        if not self.configured():
            return _stub_create(
                source=self.name,
                start_dt=kwargs["start_dt"],
                end_dt=kwargs["end_dt"],
                summary=kwargs.get("summary") or "",
            )
        shared.create_event(**kwargs)
        return {
            "ok": True,
            "created": True,
            "stub": False,
            "source": self.name,
            "summary": kwargs.get("summary") or "",
            "start": kwargs["start_dt"].isoformat(),
            "end": kwargs["end_dt"].isoformat(),
        }


class _CalDavProvider:
    """Generic CalDAV provider (Yandex etc.)."""

    name = "caldav"
    url_env = ""
    user_env = ""
    password_env = ""
    calendar_url_env = ""
    default_url = ""

    def _creds(self) -> tuple[str, str, str, str]:
        url = os.getenv(self.url_env, self.default_url).strip() or self.default_url
        user = os.getenv(self.user_env, "").strip()
        password = os.getenv(self.password_env, "").strip()
        cal_url = os.getenv(self.calendar_url_env, "").strip()
        return url, user, password, cal_url

    def configured(self) -> bool:
        _url, user, password, cal_url = self._creds()
        return bool(user and password and cal_url)

    def _calendar(self):
        url, user, password, cal_url = self._creds()
        if not (user and password and cal_url):
            raise RuntimeError(f"{self.name}_not_configured")
        client = caldav.DAVClient(url=url, username=user, password=password)
        return caldav.Calendar(client=client, url=cal_url)

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.configured():
            return True
        cal = self._calendar()
        conflicts = list(cal.search(start=start_dt, end=end_dt, event=True) or [])
        return len(conflicts) == 0

    def suggest_slots(
        self,
        desired_start: datetime,
        *,
        duration_min: int = 30,
        suggestions_count: int = 3,
        search_hours_ahead: int = 72,
    ) -> list[dict]:
        if not self.configured():
            return _stub_suggestions(
                desired_start,
                duration_min=duration_min,
                suggestions_count=suggestions_count,
                search_hours_ahead=search_hours_ahead,
                source=self.name,
            )
        suggestions: list[dict] = []
        current = desired_start
        end_limit = desired_start + timedelta(hours=search_hours_ahead)
        duration = timedelta(minutes=duration_min)
        while current + duration <= end_limit and len(suggestions) < suggestions_count:
            candidate_end = current + duration
            if self.slot_is_free(current, candidate_end):
                suggestions.append(
                    {
                        "start": current.isoformat(),
                        "end": candidate_end.isoformat(),
                        "label": shared.format_slot(current),
                        "duration_min": duration_min,
                        "source": self.name,
                    }
                )
            current += timedelta(minutes=30)
        return suggestions

    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        if not self.configured():
            return _stub_create(
                source=self.name,
                start_dt=kwargs["start_dt"],
                end_dt=kwargs["end_dt"],
                summary=kwargs.get("summary") or "",
            )
        cal = self._calendar()
        ics = shared.create_ics(
            start_dt=kwargs["start_dt"],
            end_dt=kwargs["end_dt"],
            summary=kwargs.get("summary") or "",
            description=kwargs.get("description") or "",
            location=kwargs.get("location") or "",
            attendee_email=kwargs.get("attendee_email") or "",
            event_url=kwargs.get("event_url") or "",
        )
        cal.save_event(ics)
        return {
            "ok": True,
            "created": True,
            "stub": False,
            "source": self.name,
            "summary": kwargs.get("summary") or "",
            "start": kwargs["start_dt"].isoformat(),
            "end": kwargs["end_dt"].isoformat(),
        }


class YandexProvider(_CalDavProvider):
    name = "yandex"
    url_env = "YANDEX_CALDAV_URL"
    user_env = "YANDEX_CALDAV_USERNAME"
    password_env = "YANDEX_CALDAV_PASSWORD"
    calendar_url_env = "YANDEX_CALENDAR_URL"
    default_url = "https://caldav.yandex.ru"

    def configured(self) -> bool:
        # Allow falling back to shared Mail.ru-style vars only if explicitly yandex user set,
        # or accept dedicated yandex envs. Also accept YANDEX_* filled.
        url, user, password, cal_url = self._creds()
        if user and password and cal_url:
            return True
        # Convenience: YANDEX_LOGIN + app password + calendar href
        user = os.getenv("YANDEX_LOGIN", "").strip() or user
        password = os.getenv("YANDEX_APP_PASSWORD", "").strip() or password
        return bool(user and password and cal_url)


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


class GoogleProvider:
    name = "google"

    def configured(self) -> bool:
        return bool(GOOGLE_CALENDAR_TOKEN)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {GOOGLE_CALENDAR_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ava-calendar/google",
        }

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.configured():
            return True
        cal_id = urllib.parse.quote(GOOGLE_CALENDAR_ID, safe="@")
        body = json.dumps(
            {
                "timeMin": start_dt.isoformat(),
                "timeMax": end_dt.isoformat(),
                "items": [{"id": GOOGLE_CALENDAR_ID}],
            }
        ).encode("utf-8")
        url = f"{GOOGLE_CALENDAR_API}/freeBusy"
        meta = _http_json(url, headers=self._headers(), method="POST", data=body)
        busy = ((meta.get("calendars") or {}).get(GOOGLE_CALENDAR_ID) or {}).get("busy") or []
        return len(busy) == 0

    def suggest_slots(
        self,
        desired_start: datetime,
        *,
        duration_min: int = 30,
        suggestions_count: int = 3,
        search_hours_ahead: int = 72,
    ) -> list[dict]:
        if not self.configured():
            return _stub_suggestions(
                desired_start,
                duration_min=duration_min,
                suggestions_count=suggestions_count,
                search_hours_ahead=search_hours_ahead,
                source=self.name,
            )
        suggestions: list[dict] = []
        current = desired_start
        end_limit = desired_start + timedelta(hours=search_hours_ahead)
        duration = timedelta(minutes=duration_min)
        while current + duration <= end_limit and len(suggestions) < suggestions_count:
            candidate_end = current + duration
            if self.slot_is_free(current, candidate_end):
                suggestions.append(
                    {
                        "start": current.isoformat(),
                        "end": candidate_end.isoformat(),
                        "label": shared.format_slot(current),
                        "duration_min": duration_min,
                        "source": self.name,
                    }
                )
            current += timedelta(minutes=30)
        return suggestions

    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        if not self.configured():
            return _stub_create(
                source=self.name,
                start_dt=kwargs["start_dt"],
                end_dt=kwargs["end_dt"],
                summary=kwargs.get("summary") or "",
            )
        cal_id = urllib.parse.quote(GOOGLE_CALENDAR_ID, safe="@")
        payload: dict[str, Any] = {
            "summary": kwargs.get("summary") or "Meeting",
            "description": kwargs.get("description") or "",
            "location": kwargs.get("location") or "",
            "start": {"dateTime": kwargs["start_dt"].isoformat()},
            "end": {"dateTime": kwargs["end_dt"].isoformat()},
        }
        if kwargs.get("attendee_email"):
            payload["attendees"] = [{"email": kwargs["attendee_email"]}]
        if kwargs.get("event_url"):
            payload["description"] = (
                (payload.get("description") or "") + f"\n{kwargs['event_url']}"
            ).strip()
        url = f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events"
        meta = _http_json(
            url,
            headers=self._headers(),
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
        )
        return {
            "ok": True,
            "created": True,
            "stub": False,
            "source": self.name,
            "event_id": meta.get("id"),
            "html_link": meta.get("htmlLink"),
            "summary": kwargs.get("summary") or "",
            "start": kwargs["start_dt"].isoformat(),
            "end": kwargs["end_dt"].isoformat(),
        }


class OutlookProvider:
    name = "outlook"

    def configured(self) -> bool:
        return bool(OUTLOOK_CALENDAR_TOKEN)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {OUTLOOK_CALENDAR_TOKEN}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ava-calendar/outlook",
        }

    def _calendar_path(self) -> str:
        if OUTLOOK_CALENDAR_ID:
            return f"/me/calendars/{urllib.parse.quote(OUTLOOK_CALENDAR_ID)}/events"
        return "/me/calendar/events"

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.configured():
            return True
        # calendarView getSchedule is heavier; use calendarView overlap query
        params = urllib.parse.urlencode(
            {
                "startDateTime": start_dt.isoformat(),
                "endDateTime": end_dt.isoformat(),
                "$select": "id,subject,start,end",
                "$top": "5",
            }
        )
        path = "/me/calendarView"
        url = f"{GRAPH_API}{path}?{params}"
        meta = _http_json(url, headers=self._headers())
        return len(meta.get("value") or []) == 0

    def suggest_slots(
        self,
        desired_start: datetime,
        *,
        duration_min: int = 30,
        suggestions_count: int = 3,
        search_hours_ahead: int = 72,
    ) -> list[dict]:
        if not self.configured():
            return _stub_suggestions(
                desired_start,
                duration_min=duration_min,
                suggestions_count=suggestions_count,
                search_hours_ahead=search_hours_ahead,
                source=self.name,
            )
        suggestions: list[dict] = []
        current = desired_start
        end_limit = desired_start + timedelta(hours=search_hours_ahead)
        duration = timedelta(minutes=duration_min)
        while current + duration <= end_limit and len(suggestions) < suggestions_count:
            candidate_end = current + duration
            if self.slot_is_free(current, candidate_end):
                suggestions.append(
                    {
                        "start": current.isoformat(),
                        "end": candidate_end.isoformat(),
                        "label": shared.format_slot(current),
                        "duration_min": duration_min,
                        "source": self.name,
                    }
                )
            current += timedelta(minutes=30)
        return suggestions

    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        if not self.configured():
            return _stub_create(
                source=self.name,
                start_dt=kwargs["start_dt"],
                end_dt=kwargs["end_dt"],
                summary=kwargs.get("summary") or "",
            )
        payload: dict[str, Any] = {
            "subject": kwargs.get("summary") or "Meeting",
            "body": {
                "contentType": "Text",
                "content": kwargs.get("description") or "",
            },
            "start": {
                "dateTime": kwargs["start_dt"].replace(tzinfo=None).isoformat(),
                "timeZone": shared.CALENDAR_TIMEZONE,
            },
            "end": {
                "dateTime": kwargs["end_dt"].replace(tzinfo=None).isoformat(),
                "timeZone": shared.CALENDAR_TIMEZONE,
            },
            "location": {"displayName": kwargs.get("location") or ""},
        }
        if kwargs.get("attendee_email"):
            payload["attendees"] = [
                {
                    "emailAddress": {"address": kwargs["attendee_email"]},
                    "type": "required",
                }
            ]
        url = f"{GRAPH_API}{self._calendar_path()}"
        meta = _http_json(
            url,
            headers=self._headers(),
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
        )
        return {
            "ok": True,
            "created": True,
            "stub": False,
            "source": self.name,
            "event_id": meta.get("id"),
            "web_link": meta.get("webLink"),
            "summary": kwargs.get("summary") or "",
            "start": kwargs["start_dt"].isoformat(),
            "end": kwargs["end_dt"].isoformat(),
        }


_REGISTRY: dict[str, CalendarProvider] = {
    "mailru": MailruProvider(),
    "yandex": YandexProvider(),
    "google": GoogleProvider(),
    "outlook": OutlookProvider(),
}

# aliases
_ALIASES = {
    "mail": "mailru",
    "mail.ru": "mailru",
    "ya": "yandex",
    "yandex_calendar": "yandex",
    "gcal": "google",
    "google_calendar": "google",
    "ms": "outlook",
    "office365": "outlook",
    "graph": "outlook",
}


def normalize_source(source: Optional[str]) -> str:
    raw = (source or DEFAULT_SOURCE or "mailru").strip().lower()
    raw = _ALIASES.get(raw, raw)
    if raw not in _REGISTRY:
        raise ValueError(f"unknown calendar source: {source}")
    return raw


def get_provider(source: Optional[str] = None) -> CalendarProvider:
    return _REGISTRY[normalize_source(source)]


def list_providers() -> list[dict[str, Any]]:
    items = []
    for name in PROVIDER_NAMES:
        p = _REGISTRY[name]
        items.append(
            {
                "source": name,
                "configured": p.configured(),
                "default": name == normalize_source(DEFAULT_SOURCE),
            }
        )
    return items


def providers_status() -> dict[str, Any]:
    return {
        "default_source": normalize_source(DEFAULT_SOURCE),
        "providers": list_providers(),
        "creds_policy": "tools_first",
    }
