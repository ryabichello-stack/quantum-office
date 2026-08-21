"""Campaign run control: play / pause / stop.

Independent of one-shot tests. Mass sending only while state == playing.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from core.registry import AppContext

logger = logging.getLogger("ava-outreach.runner")

STATES = ("stopped", "paused", "playing")


class RunController:
    """Persists OUTREACH_RUN_STATE via settings; exposes thread-safe transitions."""

    def __init__(self, settings: Any) -> None:
        self._settings = settings
        self._lock = threading.RLock()
        # Ensure key exists
        current = (settings.get("OUTREACH_RUN_STATE", "stopped") or "stopped").lower()
        if current not in STATES:
            current = "stopped"
            settings.set_many({"OUTREACH_RUN_STATE": current})
        self._sync_legacy(current)

    def _read_state(self) -> str:
        raw = (self._settings.get("OUTREACH_RUN_STATE", "stopped") or "stopped").lower()
        return raw if raw in STATES else "stopped"

    def state(self) -> str:
        with self._lock:
            return self._read_state()

    def _sync_legacy(self, state: str) -> None:
        """Keep OUTREACH_ENABLED / SCHEDULE_ENABLED aligned for older code paths."""
        playing = state == "playing"
        self._settings.set_many(
            {
                "OUTREACH_RUN_STATE": state,
                "OUTREACH_ENABLED": "true" if playing else "false",
                # Auto-runner owns pacing; schedule flag mirrors playing for status clarity
                "SCHEDULE_ENABLED": "true" if playing else "false",
            }
        )

    def play(self) -> dict[str, Any]:
        with self._lock:
            prev = self._read_state()
            self._sync_legacy("playing")
            logger.info("run control: %s → playing", prev)
            return {"ok": True, "state": "playing", "previous": prev}

    def pause(self) -> dict[str, Any]:
        with self._lock:
            prev = self._read_state()
            if prev == "stopped":
                return {
                    "ok": False,
                    "error": "already stopped — press Play to start",
                    "state": prev,
                }
            self._sync_legacy("paused")
            logger.info("run control: %s → paused", prev)
            return {"ok": True, "state": "paused", "previous": prev}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            prev = self._read_state()
            self._sync_legacy("stopped")
            logger.info("run control: %s → stopped", prev)
            return {"ok": True, "state": "stopped", "previous": prev}

    def status(self) -> dict[str, Any]:
        st = self.state()
        return {
            "ok": True,
            "state": st,
            "playing": st == "playing",
            "paused": st == "paused",
            "stopped": st == "stopped",
            "label": {"playing": "Play", "paused": "Pause", "stopped": "Stop"}[st],
        }


class CampaignRunner(threading.Thread):
    """Background loop: while playing, send small batches with delays."""

    def __init__(
        self,
        *,
        controller: RunController,
        settings_get: Callable[[str, str | None], str | None],
        settings_bool: Callable[[str, bool], bool],
        settings_int: Callable[[str, int], int],
        send_fn: Callable[[int], dict[str, Any]],
    ) -> None:
        super().__init__(daemon=True, name="outreach-campaign")
        self._controller = controller
        self._settings_get = settings_get
        self._settings_bool = settings_bool
        self._settings_int = settings_int
        self._send_fn = send_fn
        self._shutdown = threading.Event()
        self.last_tick: dict[str, Any] | None = None

    def shutdown(self) -> None:
        self._shutdown.set()

    def _in_window(self) -> bool:
        # Respect window only if RUN_RESPECT_WINDOW=true (default true)
        if not self._settings_bool("RUN_RESPECT_WINDOW", True):
            return True
        # Per-recipient local B2B slots (Tue–Thu preferred, dual daytime windows).
        # Broad gate: run while any Russian offset is inside a slot; sender filters.
        if self._settings_bool("SCHEDULE_LOCAL_WINDOWS", True):
            try:
                from geo_schedule import any_russian_window_open

                return any_russian_window_open(settings=self._settings_get)
            except Exception:  # noqa: BLE001
                logger.exception("local window check failed; fall back to global")
        tz_name = self._settings_get("SCHEDULE_TIMEZONE", "Europe/Moscow") or "Europe/Moscow"
        try:
            tz = ZoneInfo(tz_name)
        except Exception:  # noqa: BLE001
            tz = ZoneInfo("Europe/Moscow")
        now = datetime.now(tz)
        start = max(0, min(23, self._settings_int("SCHEDULE_WINDOW_START", 10)))
        end = max(0, min(24, self._settings_int("SCHEDULE_WINDOW_END", 18)))
        if start == end:
            return True
        if start < end:
            return start <= now.hour < end
        return now.hour >= start or now.hour < end

    def run(self) -> None:
        logger.info("campaign runner started")
        while not self._shutdown.is_set():
            state = self._controller.state()
            try:
                if state == "playing":
                    if not self._in_window():
                        self.last_tick = {
                            "at": datetime.utcnow().isoformat() + "Z",
                            "skipped": "outside_window",
                        }
                        self._shutdown.wait(15)
                        continue
                    batch = max(1, min(10, self._settings_int("SCHEDULE_BATCH_SIZE", 1)))
                    result = self._send_fn(batch)
                    self.last_tick = {
                        "at": datetime.utcnow().isoformat() + "Z",
                        "result": {
                            "ok": result.get("ok"),
                            "processed": result.get("processed"),
                            "error": result.get("error"),
                            "sent_today": result.get("sent_today"),
                            "effective_daily_limit": result.get("effective_daily_limit"),
                        },
                    }
                    logger.info("campaign tick: %s", self.last_tick)
                    # If daily limit / nothing pending — back off
                    if not result.get("ok") or int(result.get("processed") or 0) == 0:
                        self._shutdown.wait(
                            max(30, self._settings_int("SCHEDULE_TICK_SECONDS", 300))
                        )
                    else:
                        # Between batches use configured delay floor
                        self._shutdown.wait(
                            max(5, self._settings_int("OUTREACH_DELAY_MIN_SECONDS", 60))
                        )
                elif state == "paused":
                    self.last_tick = {
                        "at": datetime.utcnow().isoformat() + "Z",
                        "skipped": "paused",
                    }
                    self._shutdown.wait(2)
                else:
                    self.last_tick = {
                        "at": datetime.utcnow().isoformat() + "Z",
                        "skipped": "stopped",
                    }
                    self._shutdown.wait(3)
            except Exception:  # noqa: BLE001
                logger.exception("campaign tick failed")
                self._shutdown.wait(10)
        logger.info("campaign runner stopped")


class RunnerModule:
    name = "runner"
    version = "1.0.0"

    def __init__(self) -> None:
        self.controller: RunController | None = None
        self.campaign: CampaignRunner | None = None
        self._send_fn: Callable[[int], dict[str, Any]] | None = None

    def init_db(self) -> None:
        return None

    def bind_send_fn(self, send_fn: Callable[[int], dict[str, Any]]) -> None:
        self._send_fn = send_fn

    def on_startup(self, ctx: AppContext) -> None:
        self.controller = RunController(ctx.settings)
        ctx.extras["runner"] = self.controller
        if self._send_fn is None:
            logger.warning("runner: send_fn not bound — campaign idle")
            return
        self.campaign = CampaignRunner(
            controller=self.controller,
            settings_get=ctx.settings.get,
            settings_bool=ctx.settings.get_bool,
            settings_int=ctx.settings.get_int,
            send_fn=self._send_fn,
        )
        self.campaign.start()
        logger.info("runner module ready state=%s", self.controller.state())

    def on_shutdown(self) -> None:
        if self.campaign is not None:
            self.campaign.shutdown()
            self.campaign.join(timeout=5)
            self.campaign = None

    def health(self) -> dict[str, Any]:
        st = self.controller.status() if self.controller else {"state": "unknown"}
        tick = self.campaign.last_tick if self.campaign else None
        return {"ok": True, **st, "last_tick": tick}

    def register_routes(self, router: Any) -> None:
        from fastapi import HTTPException

        @router.get("/status")
        def status() -> dict[str, Any]:
            if not self.controller:
                raise HTTPException(503, "runner not ready")
            out = self.controller.status()
            out["last_tick"] = self.campaign.last_tick if self.campaign else None
            return out

        @router.post("/play")
        def play() -> dict[str, Any]:
            if not self.controller:
                raise HTTPException(503, "runner not ready")
            return self.controller.play()

        @router.post("/pause")
        def pause() -> dict[str, Any]:
            if not self.controller:
                raise HTTPException(503, "runner not ready")
            result = self.controller.pause()
            if not result.get("ok"):
                raise HTTPException(400, result.get("error") or "pause failed")
            return result

        @router.post("/stop")
        def stop() -> dict[str, Any]:
            if not self.controller:
                raise HTTPException(503, "runner not ready")
            return self.controller.stop()
