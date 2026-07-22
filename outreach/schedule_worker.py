"""Optional auto-send schedule within a daily time window."""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

logger = logging.getLogger("ava-outreach.schedule")


class ScheduleThread(threading.Thread):
    def __init__(
        self,
        *,
        settings_get: Callable[[str, str | None], str | None],
        settings_bool: Callable[[str, bool], bool],
        settings_int: Callable[[str, int], int],
        send_fn: Callable[[int], dict[str, Any]],
    ) -> None:
        super().__init__(daemon=True, name="outreach-schedule")
        self._settings_get = settings_get
        self._settings_bool = settings_bool
        self._settings_int = settings_int
        self._send_fn = send_fn
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def _in_window(self) -> bool:
        tz_name = self._settings_get("SCHEDULE_TIMEZONE", "Europe/Moscow") or "Europe/Moscow"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Europe/Moscow")
        now = datetime.now(tz)
        start = self._settings_int("SCHEDULE_WINDOW_START", 10)
        end = self._settings_int("SCHEDULE_WINDOW_END", 18)
        start = max(0, min(23, start))
        end = max(0, min(24, end))
        if start == end:
            return True
        if start < end:
            return start <= now.hour < end
        # overnight window
        return now.hour >= start or now.hour < end

    def run(self) -> None:
        logger.info("schedule thread started")
        while not self._stop.is_set():
            tick = max(30, self._settings_int("SCHEDULE_TICK_SECONDS", 300))
            try:
                if self._settings_bool("SCHEDULE_ENABLED", False) and self._in_window():
                    if not self._settings_bool("OUTREACH_ENABLED", False):
                        logger.info("schedule tick skipped: OUTREACH_ENABLED=false")
                    else:
                        batch = max(1, min(20, self._settings_int("SCHEDULE_BATCH_SIZE", 1)))
                        result = self._send_fn(batch)
                        logger.info("schedule send: %s", result)
                else:
                    logger.debug("schedule idle")
            except Exception:  # noqa: BLE001
                logger.exception("schedule tick failed")
            self._stop.wait(tick)
        logger.info("schedule thread stopped")
