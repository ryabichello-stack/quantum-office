"""Pace first-touch queue — soft spread across weekdays (skip weekends)."""

from __future__ import annotations

import logging
import math
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
    configured = max(1, int(effective_daily_limit or 15))
    if settings is not None and hasattr(settings, "get_int"):
        override = settings.get_int("OUTREACH_FIRST_TOUCH_DAILY_CAP", 0)
        if override and override > 0:
            return max(1, min(int(override), configured))
    # Keep ~30% of daily budget for follow-ups
    reserve = max(2, min(configured // 3, configured - 1)) if configured > 1 else 0
    return max(1, configured - reserve)


def weekday_horizon(*, start: date | None = None, workdays: int = 14) -> list[date]:
    """Next N Mon–Fri dates (today included if weekday). Weekends skipped."""
    workdays = max(1, min(int(workdays or 14), 60))
    d = start or _msk_today()
    out: list[date] = []
    guard = 0
    while len(out) < workdays and guard < workdays * 4:
        if d.weekday() < 5:  # Mon=0 … Fri=4
            out.append(d)
        d += timedelta(days=1)
        guard += 1
    return out


def pace_first_touch_queue(
    outbox: Any,
    *,
    settings: Any = None,
    effective_daily_limit: int = 15,
    workdays: int = 14,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Assign not_before across the next ``workdays`` weekdays (skip Sat/Sun).

    Soft even spread: ~ceil(pending / days) per day, never above first-touch SMTP cap.
    If backlog is larger than days×cap, extend weekday horizon until it fits.
    """
    cap = first_touch_daily_cap(settings, effective_daily_limit=effective_daily_limit)
    today = _msk_today()
    pending = outbox.list_pending_all(limit=8000)
    n = len(pending)
    if not n:
        return {
            "ok": True,
            "paced": 0,
            "today_unlocked": 0,
            "days_used": 0,
            "workdays": workdays,
            "per_day_target": 0,
            "first_touch_daily_cap": cap,
            "effective_daily_limit": effective_daily_limit,
            "by_day": {},
            "note": "Нет pending — раскладывать нечего",
        }

    days_needed = max(int(workdays or 14), int(math.ceil(n / max(1, cap))))
    days_needed = min(days_needed, 60)
    send_days = weekday_horizon(start=today, workdays=days_needed)
    if not send_days:
        send_days = [today]

    # Soft even spread across the chosen weekdays
    per_day = int(math.ceil(n / len(send_days)))
    per_day = max(1, min(per_day, cap))

    assignments: list[tuple[int, str | None, str]] = []
    idx = 0
    for day in send_days:
        if idx >= n:
            break
        slot_n = 0
        while idx < n and slot_n < per_day:
            row = pending[idx]
            idx += 1
            if day == today:
                assignments.append((row.id, None, day.isoformat()))
            else:
                assignments.append((row.id, _day_start_utc(day), day.isoformat()))
            slot_n += 1

    # Overflow if any (should be rare after days_needed math)
    overflow = 0
    while idx < n:
        row = pending[idx]
        idx += 1
        overflow += 1
        extra = send_days[-1] + timedelta(days=1)
        while extra.weekday() >= 5:
            extra += timedelta(days=1)
        send_days.append(extra)
        assignments.append((row.id, _day_start_utc(extra), extra.isoformat()))

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
        "workdays": len(send_days),
        "per_day_target": per_day,
        "first_touch_daily_cap": cap,
        "effective_daily_limit": effective_daily_limit,
        "by_day": dict(sorted(by_day.items())),
        "overflow": overflow,
        "dry_run": dry_run,
        "weekends_skipped": True,
        "note": (
            f"Очередь разложена на {len(by_day)} будних дней (~{per_day}/день), "
            f"выходные пропущены. Сегодня разблокировано {today_unlocked} "
            f"(SMTP-лимит {effective_daily_limit}, first-touch cap {cap})."
        ),
    }
