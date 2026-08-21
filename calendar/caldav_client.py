"""Mail.ru CalDAV helpers for the standalone calendar service."""

from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, List, Optional

import caldav
import pytz
from dateutil import parser as dtparser
from fastapi import HTTPException
from icalendar import Calendar, Event

logger = logging.getLogger(__name__)

MAILRU_CALDAV_URL = os.getenv("MAILRU_CALDAV_URL", "https://calendar.mail.ru").strip()
MAILRU_CALDAV_USERNAME = os.getenv("MAILRU_CALDAV_USERNAME", "").strip()
MAILRU_CALDAV_PASSWORD = os.getenv("MAILRU_CALDAV_PASSWORD", "").strip()
MAILRU_CALENDAR_URL = os.getenv("MAILRU_CALENDAR_URL", "").strip()
CALENDAR_DEFAULT_DURATION_MIN = int(os.getenv("CALENDAR_DEFAULT_DURATION_MIN", "30") or "30")
CALENDAR_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "Europe/Moscow").strip() or "Europe/Moscow"


def credentials_configured() -> bool:
    return bool(MAILRU_CALDAV_USERNAME and MAILRU_CALDAV_PASSWORD and MAILRU_CALENDAR_URL)


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).strip()


def clean_email(value: Optional[str]) -> str:
    email = clean_text(value).replace(" ", "")
    if not email:
        return ""
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        return email
    logger.warning("invalid attendee_email=%r", email)
    return ""


def tz(name: Optional[str] = None) -> pytz.BaseTzInfo:
    try:
        return pytz.timezone(name or CALENDAR_TIMEZONE)
    except Exception:
        return pytz.timezone(CALENDAR_TIMEZONE)


def parse_dt(value: str, tz_name: Optional[str] = None) -> datetime:
    zone = tz(tz_name)
    dt = dtparser.parse(value)
    if dt.tzinfo is None:
        return zone.localize(dt)
    return dt.astimezone(zone)


def get_calendar():
    if not credentials_configured():
        raise HTTPException(
            status_code=500,
            detail="Mail.ru calendar credentials are not configured",
        )
    client = caldav.DAVClient(
        url=MAILRU_CALDAV_URL,
        username=MAILRU_CALDAV_USERNAME,
        password=MAILRU_CALDAV_PASSWORD,
    )
    return caldav.Calendar(client=client, url=MAILRU_CALENDAR_URL)


def find_conflicts(start_dt: datetime, end_dt: datetime) -> List[Any]:
    cal = get_calendar()
    return list(cal.search(start=start_dt, end=end_dt, event=True) or [])


def slot_is_free(start_dt: datetime, end_dt: datetime) -> bool:
    return len(find_conflicts(start_dt, end_dt)) == 0


def format_slot(dt: datetime) -> str:
    return dt.strftime("%d.%m.%Y %H:%M")


def create_ics(
    *,
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
    description: str = "",
    location: str = "",
    attendee_email: str = "",
    event_url: str = "",
) -> str:
    cal = Calendar()
    cal.add("prodid", "-//Quantum Labs//AVA Calendar Service//RU")
    cal.add("version", "2.0")

    event = Event()
    event.add("summary", summary)
    event.add("dtstart", start_dt)
    event.add("dtend", end_dt)
    event.add("dtstamp", datetime.utcnow())
    event.add("description", description or "")

    if location:
        event.add("location", location)

    url = clean_text(event_url)
    if not url and location.startswith("http"):
        url = location
    if url:
        event.add("url", url)
    if attendee_email:
        event.add("attendee", f"MAILTO:{attendee_email}")

    cal.add_component(event)
    return cal.to_ical().decode("utf-8")


def create_event(
    *,
    start_dt: datetime,
    end_dt: datetime,
    summary: str,
    description: str = "",
    location: str = "",
    attendee_email: str = "",
    event_url: str = "",
):
    cal = get_calendar()
    ics = create_ics(
        start_dt=start_dt,
        end_dt=end_dt,
        summary=summary,
        description=description,
        location=location,
        attendee_email=attendee_email,
        event_url=event_url,
    )
    return cal.save_event(ics)


def suggest_slots(
    desired_start: datetime,
    duration_min: int = 30,
    suggestions_count: int = 3,
    search_hours_ahead: int = 72,
) -> List[dict]:
    suggestions: List[dict] = []
    current = desired_start
    end_limit = desired_start + timedelta(hours=search_hours_ahead)
    duration = timedelta(minutes=duration_min)

    while current + duration <= end_limit and len(suggestions) < suggestions_count:
        candidate_end = current + duration
        if slot_is_free(current, candidate_end):
            suggestions.append(
                {
                    "start": current.isoformat(),
                    "end": candidate_end.isoformat(),
                    "label": format_slot(current),
                }
            )
        current += timedelta(minutes=30)

    return suggestions
