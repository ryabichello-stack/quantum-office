"""Email Reputation Guard — thresholds + campaign/route pause (no domain rotation)."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from core.paths import MODULES_DB, SETTINGS_DB
from core.registry import AppContext

logger = logging.getLogger("ava-outreach.reputation_guard")

# Defaults — overridable via RuntimeSettings keys.
DEFAULTS = {
    "REP_POLICY_ISP_PAUSE": 3,  # distinct ISP families → pause mailbox
    "REP_HARD_RATE_PCT": 3.0,
    "REP_HARD_MIN_WINDOW": 20,
    "REP_HARD_MIN_COUNT": 3,
    "REP_AUTH_PAUSE": 1,
    "REP_POLICY_CAMPAIGN_PAUSE": 2,  # policy events on same campaign today
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class ReputationGuardStore:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path or MODULES_DB)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_pause (
                    campaign TEXT PRIMARY KEY,
                    paused INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                )
                """
            )

    def is_campaign_paused(self, campaign: str) -> tuple[bool, str]:
        key = (campaign or "default").strip() or "default"
        with self.connect() as conn:
            row = conn.execute(
                "SELECT paused, reason FROM campaign_pause WHERE campaign = ?",
                (key,),
            ).fetchone()
        if not row:
            return False, ""
        return bool(row["paused"]), str(row["reason"] or "")

    def pause_campaign(self, campaign: str, reason: str) -> None:
        key = (campaign or "default").strip() or "default"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO campaign_pause(campaign, paused, reason, updated_at)
                VALUES (?, 1, ?, ?)
                ON CONFLICT(campaign) DO UPDATE SET
                    paused = 1,
                    reason = excluded.reason,
                    updated_at = excluded.updated_at
                """,
                (key, (reason or "manual")[:500], _utc_now()),
            )
        logger.warning("campaign PAUSED %s: %s", key, reason)

    def resume_campaign(self, campaign: str) -> None:
        key = (campaign or "default").strip() or "default"
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO campaign_pause(campaign, paused, reason, updated_at)
                VALUES (?, 0, '', ?)
                ON CONFLICT(campaign) DO UPDATE SET
                    paused = 0,
                    reason = '',
                    updated_at = excluded.updated_at
                """,
                (key, _utc_now()),
            )
        logger.info("campaign resumed %s", key)

    def list_paused(self) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM campaign_pause WHERE paused = 1 ORDER BY campaign"
            ).fetchall()
        return [dict(r) for r in rows]

    def thresholds(self, settings: Any = None) -> dict[str, Any]:
        out = dict(DEFAULTS)
        if settings is None:
            return out
        for k, default in DEFAULTS.items():
            try:
                if isinstance(default, float):
                    raw = settings.get(k, default) if hasattr(settings, "get") else default
                    out[k] = float(raw if raw not in (None, "") else default)
                elif isinstance(default, int):
                    out[k] = (
                        settings.get_int(k, default)
                        if hasattr(settings, "get_int")
                        else int(settings.get(k, default) or default)
                    )
                else:
                    out[k] = settings.get(k, default)
            except Exception:  # noqa: BLE001
                out[k] = default
        return out

    def evaluate_after_policy(
        self,
        *,
        campaign: str,
        settings: Any = None,
        sending_accounts: Any = None,
    ) -> dict[str, Any]:
        """Pause campaign (not rotate domains) when policy volume on this campaign is high."""
        thr = self.thresholds(settings)
        # Count policy events today for campaign via delivery_errors if present
        n = 0
        try:
            from modules.delivery_errors import DeliveryErrorStore

            day = _today()
            store = DeliveryErrorStore(self.db_path)
            with store.connect() as conn:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM delivery_error_events
                    WHERE category = 'policy'
                      AND created_at LIKE ?
                      AND (campaign = ? OR campaign = '' OR campaign IS NULL)
                    """,
                    (f"{day}%", campaign or ""),
                ).fetchone()
                n = int(row["n"]) if row else 0
        except Exception:  # noqa: BLE001
            logger.debug("policy campaign count failed", exc_info=True)

        limit = int(thr["REP_POLICY_CAMPAIGN_PAUSE"])
        if n >= limit:
            reason = f"reputation_guard:policy_events_today={n}>={limit}"
            self.pause_campaign(campaign or "default", reason)
            if sending_accounts is not None:
                try:
                    sending_accounts.record_incident(
                        account_id="legacy",
                        campaign=campaign or "default",
                        kind="policy_threshold",
                        detail=reason,
                        action="pause_campaign",
                    )
                    sending_accounts.set_health(
                        "legacy",
                        "WARNING",
                        detail=reason,
                    )
                except Exception:  # noqa: BLE001
                    logger.debug("incident notify failed", exc_info=True)
            self._notify(reason, settings)
            return {"paused": True, "reason": reason, "policy_today": n}
        return {"paused": False, "reason": "", "policy_today": n}

    def _notify(self, reason: str, settings: Any) -> None:
        try:
            from ops_notify import notify_mailbox_paused
            from runtime_settings import RuntimeSettings

            rt = settings if settings is not None else RuntimeSettings(SETTINGS_DB)
            notify_mailbox_paused(reason=reason, settings=rt)
        except Exception:  # noqa: BLE001
            logger.debug("ops notify failed", exc_info=True)


class ReputationGuardModule:
    name = "reputation_guard"
    version = "1.0.0"

    def __init__(self) -> None:
        self.store = ReputationGuardStore()
        self._settings: Any = None

    def init_db(self) -> None:
        self.store.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        self._settings = ctx.settings
        ctx.extras["reputation_guard"] = self.store
        logger.info("reputation_guard ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        return {"ok": True, "paused_campaigns": self.store.list_paused()}

    def register_routes(self, router: Any) -> None:
        from pydantic import BaseModel

        @router.get("/status")
        def status() -> dict[str, Any]:
            return {
                "ok": True,
                "thresholds": self.store.thresholds(self._settings),
                "paused": self.store.list_paused(),
            }

        class PauseBody(BaseModel):
            campaign: str = "default"
            reason: str = "manual"

        @router.post("/pause")
        def pause(body: PauseBody) -> dict[str, Any]:
            self.store.pause_campaign(body.campaign, body.reason)
            return {"ok": True, "paused": self.store.list_paused()}

        @router.post("/resume")
        def resume(campaign: str = "default") -> dict[str, Any]:
            self.store.resume_campaign(campaign)
            return {"ok": True, "paused": self.store.list_paused()}
