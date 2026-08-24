"""Anti-spam pacing: spread first-touch across weekdays."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from modules.sequences.pace import first_touch_daily_cap, pace_first_touch_queue, weekday_horizon
from outbox import OutboxStore


def test_first_touch_cap_reserves_followups():
    settings = MagicMock()
    settings.get_int.return_value = 0
    assert first_touch_daily_cap(settings, effective_daily_limit=15) == 10  # ~30% reserve
    assert first_touch_daily_cap(settings, effective_daily_limit=5) == 3


def test_weekday_horizon_skips_weekend():
    from datetime import date

    # 2026-08-24 is Monday
    days = weekday_horizon(start=date(2026, 8, 24), workdays=10)
    assert len(days) == 10
    assert all(d.weekday() < 5 for d in days)
    assert date(2026, 8, 29) not in days  # Saturday
    assert date(2026, 8, 30) not in days  # Sunday


def test_pace_spreads_evenly_over_workdays():
    with tempfile.TemporaryDirectory() as tmp:
        store = OutboxStore(Path(tmp) / "o.db")
        for i in range(70):
            store.upsert_company(
                email=f"c{i}@example.com",
                company_id=str(i),
                company_title=f"C{i}",
            )
        settings = MagicMock()
        settings.get_int.side_effect = lambda k, d=0: {
            "OUTREACH_FIRST_TOUCH_DAILY_CAP": 5,
        }.get(k, d)

        out = pace_first_touch_queue(
            store,
            settings=settings,
            effective_daily_limit=15,
            workdays=14,
            dry_run=False,
        )
        assert out["ok"] is True
        assert out["weekends_skipped"] is True
        assert out["today_unlocked"] <= 5
        assert out["days_used"] >= 10
        # no single day above cap
        assert max(out["by_day"].values()) <= 5

        ready = store.list_pending(100)
        assert len(ready) <= 5
        all_pending = store.list_pending_all(100)
        assert len(all_pending) == 70
        held = [r for r in all_pending if r.not_before]
        assert len(held) >= 60
