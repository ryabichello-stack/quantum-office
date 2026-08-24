"""Pace first-touch queue — spread pending sends across days to avoid spam filters.

Calendar may show hundreds of "ready" companies on Monday; actual SMTP is already
capped by OUTREACH_DAILY_LIMIT + warmup. This module assigns outbox.not_before so
only ~daily_cap first-touch rows become eligible each day (follow-ups stay priority).
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger("ava-outreach.pace")


def _msk_today() -> date:
    return datetime.now(ZoneInfo("Europe/Moscow")).date()


def _day_start_utc(day: date, *, hour: int = 7) -> str:
    """07:00 MSK as UTC ISO — early enough that local windows still apply later."""
    msk = ZoneInfo("Europe/Moscow")
    local = datetime(day.year, day.month, day.day, hour, 0, 0, tzinfo=msk)
    return local.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def first_touch_daily_cap(settings: Any, *, effective_daily_limit: int) -> int:
    """How many NEW first-touch emails may unlock per day (reserve room for follow-ups)."""
    configured = effective_daily_limit
    if settings is not None and hasattr(settings, "get_int"):
        override = settings.get_int("OUTREACH_FIRST_TOUCH_DAILY_CAP", 0)
        if override and override > 0:
            return max(1, min(override, configured))
    # Keep ~40% of daily budget for follow-ups (min 3, max half)
    reserve = max(3, min(configured // 2, configured - 1)) if configured > 1 else 0
    return max(1, configured - reserve)


def pace_first_touch_queue(
    outbox: Any,
    *,
    settings: Any = None,
    effective_daily_limit: int = 15,
    horizon_days: int = 45,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Assign not_before across upcoming weekdays so backlog is not all 'today'.

    Does not send. Follow-up sequences are unchanged (they use next_action_at).
    """
    from geo_schedule import schedule_config

    cfg = schedule_config(settings)
    allowed = list(cfg.get("allowed_weekdays") or [0, 1, 2, 3, 4])
    preferred = list(cfg.get("preferred_weekdays") or [1, 2, 3])
    # Prefer Tue–Thu when present, else any allowed weekday
    day_preference = [d for d in preferred if d in allowed] or list(allowed)

    cap = first_touch_daily_cap(settings, effective_daily_limit=effective_daily_limit)
    today = _msk_today()
    pending = outbox.list_pending_all(limit=8000)
    if not pending:
        return {
            "ok": True,
            "paced": 0,
            "today_unlocked": 0,
            "days_used": 0,
            "first_touch_daily_cap": cap,
            "effective_daily_limit": effective_daily_limit,
            "note": "no pending",
        }

    # Build list of send days (today + future preferred weekdays)
    send_days: list = []
    d = today
    while len(send_days) < horizon_days:
        if d.weekday() in day_preference or (not day_preference and d.weekday() in allowed):
            send_days.append(d)
        elif d == today and d.weekday() in allowed:
            # Always allow today if it's a workday even if not preferred
            send_days.append(d)
        d += timedelta(days=1)
        if (d - today).days > horizon_days + 14:
            break

    if not send_days:
        send_days = [today]

    assignments: list[tuple[int, str | None, str]] = []  # id, not_before, day_iso
    idx = 0
    for day in send_days:
        if idx >= len(pending):
            break
        slot_n = 0
        while idx < len(pending) and slot_n < cap:
            row = pending[idx]
            idx += 1
            if day == today:
                # Unlock for today — eligible immediately
                assignments.append((row.id, None, day.isoformat()))
            else:
                assignments.append((row.id, _day_start_utc(day), day.isoformat()))
            slot_n += 1

    # Any overflow beyond horizon: park on last day + staggered hours
    overflow = 0
    while idx < len(pending):
        row = pending[idx]
        idx += 1
        overflow += 1
        last = send_days[-1] + timedelta(days=1 + (overflow // max(1, cap)))
        assignments.append((row.id, _day_start_utc(last), last.isoformat()))

    if not dry_run:
        for row_id, nb, _day in assignments:
            outbox.set_not_before(row_id, nb)

    by_day: dict[str, int] = {}
    for _id, _nb, day_iso in assignments:
        by_day[day_iso] = by_day.get(day_iso, 0) + 1

    today_unlocked = by_day.get(today.isoformat(), 0)
    return {
        "ok": True,
        "paced": len(assignments),
        "today_unlocked": today_unlocked,
        "days_used": len(by_day),
        "first_touch_daily_cap": cap,
        "effective_daily_limit": effective_daily_limit,
        "by_day": dict(sorted(by_day.items())[:21]),
        "overflow": overflow,
        "dry_run": dry_run,
        "note": (
            f"Первые письма разложены по ~{cap}/день "
            f"(дневной лимит SMTP {effective_daily_limit}, часть слотов — follow-up). "
            "296 в один день больше не уйдут."
        ),
    }
