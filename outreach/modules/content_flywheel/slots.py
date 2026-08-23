"""Editorial slots — several posts per day in tenant timezone."""

from __future__ import annotations

import os
from datetime import date, datetime, time, timezone
from typing import Any
from zoneinfo import ZoneInfo


def flywheel_tz() -> ZoneInfo:
    name = (os.getenv("FLYWHEEL_TZ") or "Europe/Moscow").strip()
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001
        return ZoneInfo("Europe/Moscow")


def slot_hours() -> list[int]:
    raw = (os.getenv("FLYWHEEL_SLOT_HOURS") or "10,14,18").strip()
    hours: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            h = int(part.split(":")[0])
            if 0 <= h <= 23:
                hours.append(h)
        except ValueError:
            continue
    if not hours:
        return [10, 14, 18]
    limit = int(os.getenv("FLYWHEEL_SLOTS_PER_DAY") or "3")
    return sorted(set(hours))[: max(1, min(limit, 8))]


def slots_for_day(day: date | None = None, *, tz: ZoneInfo | None = None) -> list[dict[str, Any]]:
    tz = tz or flywheel_tz()
    day = day or datetime.now(tz).date()
    out: list[dict[str, Any]] = []
    for h in slot_hours():
        local_dt = datetime.combine(day, time(h, 0), tzinfo=tz)
        utc_dt = local_dt.astimezone(timezone.utc)
        out.append(
            {
                "slot_key": f"{day.isoformat()}T{h:02d}:00",
                "local_time": local_dt.isoformat(),
                "utc_time": utc_dt.replace(microsecond=0).isoformat(),
                "hour": h,
                "label": f"{h:02d}:00",
            }
        )
    return out


def next_open_slot(
    occupied_keys: set[str],
    *,
    tz: ZoneInfo | None = None,
) -> dict[str, Any] | None:
    tz = tz or flywheel_tz()
    now = datetime.now(tz)
    for offset in range(0, 3):
        d = (now.date()).fromordinal(now.date().toordinal() + offset)
        for slot in slots_for_day(d, tz=tz):
            key = slot["slot_key"]
            if key in occupied_keys:
                continue
            local = datetime.fromisoformat(slot["local_time"])
            if offset == 0 and local < now:
                continue
            return slot
    return None
