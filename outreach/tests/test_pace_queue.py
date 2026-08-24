"""Anti-spam pacing: spread first-touch across days."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

from modules.sequences.pace import first_touch_daily_cap, pace_first_touch_queue
from outbox import OutboxStore


def test_first_touch_cap_reserves_followups():
    settings = MagicMock()
    settings.get_int.return_value = 0
    assert first_touch_daily_cap(settings, effective_daily_limit=15) == 8  # reserve ~half, min 3
    assert first_touch_daily_cap(settings, effective_daily_limit=5) == 2


def test_pace_spreads_pending_not_all_today():
    with tempfile.TemporaryDirectory() as tmp:
        store = OutboxStore(Path(tmp) / "o.db")
        for i in range(40):
            store.upsert_company(
                email=f"c{i}@example.com",
                company_id=str(i),
                company_title=f"C{i}",
            )
        settings = MagicMock()
        settings.get_int.side_effect = lambda k, d=0: {
            "OUTREACH_FIRST_TOUCH_DAILY_CAP": 5,
        }.get(k, d)
        # schedule_config needs get/get_bool for weekdays
        settings.get.side_effect = lambda k, d="": {
            "SCHEDULE_PREFERRED_WEEKDAYS": "0,1,2,3,4",
            "SCHEDULE_ALLOWED_WEEKDAYS": "0,1,2,3,4",
        }.get(k, d)
        settings.get_bool.return_value = True

        out = pace_first_touch_queue(
            store,
            settings=settings,
            effective_daily_limit=15,
            horizon_days=30,
            dry_run=False,
        )
        assert out["ok"] is True
        assert out["today_unlocked"] <= 5
        assert out["days_used"] >= 5

        ready = store.list_pending(100)
        assert len(ready) <= 5
        all_pending = store.list_pending_all(100)
        assert len(all_pending) == 40
        held = [r for r in all_pending if r.not_before]
        assert len(held) >= 30
