"""Background flywheel cycle — poll sources + process news on interval."""

from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable

from modules.content_flywheel.ingest import flywheel_enabled

logger = logging.getLogger("ava-outreach.content_flywheel.worker")


def auto_cycle_enabled() -> bool:
    return (os.getenv("FLYWHEEL_AUTO_CYCLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def cycle_interval_seconds() -> int:
    try:
        return max(300, int(os.getenv("FLYWHEEL_CYCLE_SECONDS") or "3600"))
    except ValueError:
        return 3600


class FlywheelCycleThread(threading.Thread):
    def __init__(self, *, run_cycle_fn: Callable[[], dict[str, Any]]) -> None:
        super().__init__(daemon=True, name="flywheel-cycle")
        self._run_cycle_fn = run_cycle_fn
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        logger.info("flywheel cycle thread started interval=%ss", cycle_interval_seconds())
        while not self._stop.is_set():
            tick = cycle_interval_seconds()
            try:
                if flywheel_enabled() and auto_cycle_enabled():
                    result = self._run_cycle_fn()
                    logger.info(
                        "flywheel cycle: processed=%s skipped=%s",
                        result.get("processed"),
                        result.get("skipped"),
                    )
                else:
                    logger.debug("flywheel cycle idle (disabled)")
            except Exception:  # noqa: BLE001
                logger.exception("flywheel cycle tick failed")
            self._stop.wait(tick)
        logger.info("flywheel cycle thread stopped")
