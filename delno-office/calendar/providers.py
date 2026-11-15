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
from tenant_scope import allow_env_fallback, request_bound, request_credentials

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


def _scoped_secret(request_value: str, env_value: str) -> str:
    """Bound requests use the tenant vault value. Env only with an explicit flag."""
    if request_bound():
        if (request_value or "").strip():
            return request_value.strip()
        if allow_env_fallback():
            return (env_value or "").strip()
        return ""
    return (env_value or "").strip()


def _env_google_token() -> str:
    return (
        os.getenv("GOOGLE_CALENDAR_TOKEN", "").strip()
        or os.getenv("GOOGLE_CALENDAR_ACCESS_TOKEN", "").strip()
    )


def _env_outlook_token() -> str:
    return (
        os.getenv("OUTLOOK_CALENDAR_TOKEN", "").strip()
        or os.getenv("MICROSOFT_GRAPH_TOKEN", "").strip()
        or os.getenv("ONEDRIVE_TOKEN", "").strip()
    )


def google_token() -> str:
    return _scoped_secret(str(request_credentials().get("token") or ""), _env_google_token())


def outlook_token() -> str:
    return _scoped_secret(str(request_credentials().get("token") or ""), _env_outlook_token())


def google_calendar_id() -> str:
    requested = str(request_credentials().get("calendar_id") or "").strip()
    env_value = os.getenv("GOOGLE_CALENDAR_ID", "primary").strip() or "primary"
    if request_bound():
        if requested:
            return requested
        if allow_env_fallback():
            return env_value
        return "primary"
    return env_value


# Tests: identity → events. Enabled with CALENDAR_MEMORY_BACKEND=1. Tokens are keys, never logs.
_MEMORY_EVENTS: dict[str, list[dict[str, Any]]] = {}


def seed_memory_events(identity: str, events: list[dict[str, Any]]) -> None:
    _MEMORY_EVENTS[identity] = list(events)


def memory_backend() -> bool:
    return os.getenv("CALENDAR_MEMORY_BACKEND", "").strip().lower() in ("1", "true", "yes")


def memory_events(identity: str) -> list[dict[str, Any]]:
    return [dict(item) for item in _MEMORY_EVENTS.get(identity) or []]


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


def _events_overlap(events: list[dict[str, Any]], start_dt: datetime, end_dt: datetime) -> bool:
    for ev in events:
        ev_start = _parse_iso(str(ev.get("start") or ""))
        ev_end = _parse_iso(str(ev.get("end") or ""))
        if ev_start is None or ev_end is None:
            continue
        if ev_start < end_dt and ev_end > start_dt:
            return True
    return False


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class MailruProvider:
    name = "mailru"

    def _request_identity(self) -> tuple[str, str, str]:
        c = request_credentials()
        user = str(c.get("username") or c.get("login") or "").strip()
        password = str(c.get("password") or "").strip()
        cal_url = str(c.get("calendar_url") or "").strip()
        return user, password, cal_url

    def configured(self) -> bool:
        if request_bound():
            user, password, cal_url = self._request_identity()
            if user and password and cal_url:
                return True
            if allow_env_fallback():
                return shared.credentials_configured()
            return False
        return shared.credentials_configured()

    def identity(self) -> str:
        user, _password, _cal = self._request_identity()
        if user:
            return user
        if allow_env_fallback() or not request_bound():
            return shared.MAILRU_CALDAV_USERNAME
        return ""

    def list_events(self) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError("not_configured")
        if memory_backend():
            return memory_events(self.identity())
        cal = shared.get_calendar()
        found = list(cal.search(event=True) or [])
        return [{"summary": self.name, "source": self.name, "href": str(getattr(ev, "url", "") or "")} for ev in found]

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.configured():
            return True
        if memory_backend():
            return not _events_overlap(memory_events(self.identity()), start_dt, end_dt)
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

    def _env_creds(self) -> tuple[str, str, str, str]:
        url = os.getenv(self.url_env, self.default_url).strip() or self.default_url
        user = os.getenv(self.user_env, "").strip()
        password = os.getenv(self.password_env, "").strip()
        cal_url = os.getenv(self.calendar_url_env, "").strip()
        return url, user, password, cal_url

    def _creds(self) -> tuple[str, str, str, str]:
        url, user, password, cal_url = self._env_creds()
        c = request_credentials()
        req_user = str(c.get("username") or c.get("login") or "").strip()
        req_password = str(c.get("password") or "").strip()
        req_cal = str(c.get("calendar_url") or "").strip()
        req_url = str(c.get("url") or "").strip()
        if request_bound():
            if req_user and req_password and req_cal:
                return req_url or url or self.default_url, req_user, req_password, req_cal
            if allow_env_fallback():
                return url, user, password, cal_url
            return req_url or self.default_url, "", "", ""
        return url, user, password, cal_url

    def identity(self) -> str:
        _url, user, _password, _cal = self._creds()
        return user

    def list_events(self) -> list[dict[str, Any]]:
        if not self.configured():
            raise RuntimeError("not_configured")
        if memory_backend():
            return memory_events(self.identity())
        cal = self._calendar()
        found = list(cal.search(event=True) or [])
        items: list[dict[str, Any]] = []
        for ev in found:
            items.append({"summary": getattr(ev, "url", None) or self.name, "source": self.name})
        return items

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
        url, user, password, cal_url = self._creds()
        if user and password and cal_url:
            return True
        # Convenience env only when this call is allowed to read the server account.
        if request_bound() and not allow_env_fallback():
            return False
        user = os.getenv("YANDEX_LOGIN", "").strip() or user
        password = os.getenv("YANDEX_APP_PASSWORD", "").strip() or password
        cal_url = cal_url or os.getenv("YANDEX_CALENDAR_URL", "").strip()
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
        return bool(google_token())

    def identity(self) -> str:
        return google_token()

    def list_events(self) -> list[dict[str, Any]]:
        token = google_token()
        if not token:
            raise RuntimeError("not_configured")
        if memory_backend():
            return memory_events(token)
        cal_id = urllib.parse.quote(google_calendar_id(), safe="@")
        url = f"{GOOGLE_CALENDAR_API}/calendars/{cal_id}/events?singleEvents=true&maxResults=50"
        meta = _http_json(url, headers=self._headers())
        items = []
        for ev in meta.get("items") or []:
            items.append(
                {
                    "id": ev.get("id"),
                    "summary": ev.get("summary") or "",
                    "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
                    "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
                    "source": self.name,
                }
            )
        return items

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {google_token()}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "ava-calendar/google",
        }

    def slot_is_free(self, start_dt: datetime, end_dt: datetime) -> bool:
        if not self.configured():
            return True
        if memory_backend():
            return not _events_overlap(memory_events(self.identity()), start_dt, end_dt)
        cal_id = urllib.parse.quote(google_calendar_id(), safe="@")
        body = json.dumps(
            {
                "timeMin": start_dt.isoformat(),
                "timeMax": end_dt.isoformat(),
                "items": [{"id": google_calendar_id()}],
            }
        ).encode("utf-8")
        url = f"{GOOGLE_CALENDAR_API}/freeBusy"
        meta = _http_json(url, headers=self._headers(), method="POST", data=body)
        busy = ((meta.get("calendars") or {}).get(google_calendar_id()) or {}).get("busy") or []
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
        cal_id = urllib.parse.quote(google_calendar_id(), safe="@")
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
        return bool(outlook_token())

    def identity(self) -> str:
        return outlook_token()

    def list_events(self) -> list[dict[str, Any]]:
        token = outlook_token()
        if not token:
            raise RuntimeError("not_configured")
        if memory_backend():
            return memory_events(token)
        url = f"{GRAPH_API}{self._calendar_path()}?$top=50&$select=id,subject,start,end"
        meta = _http_json(url, headers=self._headers())
        items = []
        for ev in meta.get("value") or []:
            items.append(
                {
                    "id": ev.get("id"),
                    "summary": ev.get("subject") or "",
                    "start": (ev.get("start") or {}).get("dateTime"),
                    "end": (ev.get("end") or {}).get("dateTime"),
                    "source": self.name,
                }
            )
        return items

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {outlook_token()}",
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
        if memory_backend():
            return not _events_overlap(memory_events(self.identity()), start_dt, end_dt)
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
