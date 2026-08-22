"""Runtime settings stored in SQLite (UI-editable), layered over process env."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

# Keys the UI may read/write. Secrets are never returned in full.
EDITABLE_KEYS = (
    "OUTREACH_ENABLED",
    "OUTREACH_DAILY_LIMIT",
    "OUTREACH_DELAY_MIN_SECONDS",
    "OUTREACH_DELAY_MAX_SECONDS",
    "OUTREACH_SUBJECT",
    "OUTREACH_COMPANY_NAME",
    "OUTREACH_WEBSITE",
    "OUTREACH_CONTACT_PHONE",
    "OUTREACH_CONTACT_EMAIL",
    "OUTREACH_SIGNATURE",
    "OUTREACH_LOGO_URL",
    "OUTREACH_LOGO_ENABLED",
    "OUTREACH_UNSUBSCRIBE_MAILTO",
    "OUTREACH_TEMPLATE_PLAIN",
    "OUTREACH_TEMPLATE_HTML",
    "SCHEDULE_ENABLED",
    "SCHEDULE_WINDOW_START",
    "SCHEDULE_WINDOW_END",
    "SCHEDULE_TIMEZONE",
    "SCHEDULE_BATCH_SIZE",
    "SCHEDULE_TICK_SECONDS",
    "SCHEDULE_LOCAL_WINDOWS",
    "SCHEDULE_SLOTS",
    "SCHEDULE_PREFERRED_WEEKDAYS",
    "SCHEDULE_ALLOWED_WEEKDAYS",
    "SCHEDULE_DEFAULT_TIMEZONE",
    "SCHEDULE_PREFER_TUE_THU",
    "SCHEDULE_FOLLOWUPS_FIRST",
    "SCHEDULE_SKIP_RU_HOLIDAYS",
    "SCHEDULE_TZ_FAIRNESS",
    "OOO_PAUSE_DAYS",
    "BITRIX_CREATE_DEAL",
    "BITRIX_ASSIGNED_BY_ID",
    "BITRIX_DEAL_STAGE_ID",
    "BITRIX_TIMELINE_COMMENT",
    "REPLY_WATCH_ENABLED",
    "REPLY_NOTIFY_ENABLED",
    "REPLY_NOTIFY_EMAIL",
    # Deliverability / tracking (module settings)
    "WARMUP_ENABLED",
    "WARMUP_START_DAY",
    "DOMAIN_DAILY_CAP",
    "TRACKING_PLUS_REPLY_TO",
    "OPEN_TRACKING_ENABLED",
    "TRACKING_PUBLIC_BASE",
    "ONESHOT_DAILY_LIMIT",
    "OUTREACH_RUN_STATE",
    "RUN_RESPECT_WINDOW",
    "COMPANY_DAILY_CAP",
    "COMPANY_CONTACT_COOLDOWN_DAYS",
    "SEQUENCES_ENABLED",
    "OUTREACH_SEQUENCE_PACK",
    "OUTREACH_ATTACH_PRESENTATION",
    "OUTREACH_PRESENTATION_PDF",
    # Callback CTA from email → notify + optional AVA dial
    "CALLBACK_CTA_ENABLED",
    "CALLBACK_DIAL_ENABLED",
    "CALLBACK_NOTIFY_ENABLED",
    "CALLBACK_DIAL_MODE",
    "CALLBACK_CTA_TITLE",
    "CALLBACK_CTA_LEAD",
    "CALLBACK_CTA_BUTTON",
    "CALLBACK_NOTIFY_EMAIL",
    "CALLBACK_SCENARIO_GREETING",
    "CALLBACK_SCENARIO_SCRIPT",
)

SECRET_KEYS = frozenset(
    {
        "BITRIX_WEBHOOK_URL",
        "MAIL_PASSWORD",
        "OUTREACH_UI_TOKEN",
    }
)


class RuntimeSettings:
    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
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
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    def get(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_settings WHERE key = ?", (key,)
            ).fetchone()
        if row is not None:
            return str(row["value"])
        env = os.getenv(key)
        if env is not None:
            return env
        return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return raw.lower() in ("1", "true", "yes", "on")

    def get_int(self, key: str, default: int) -> int:
        raw = self.get(key)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def set_many(self, values: dict[str, Any]) -> dict[str, str]:
        updated: dict[str, str] = {}
        with self.connect() as conn:
            for key, value in values.items():
                if key not in EDITABLE_KEYS:
                    continue
                text = "" if value is None else str(value)
                conn.execute(
                    """
                    INSERT INTO app_settings(key, value, updated_at)
                    VALUES (?, ?, datetime('now'))
                    ON CONFLICT(key) DO UPDATE SET
                      value = excluded.value,
                      updated_at = excluded.updated_at
                    """,
                    (key, text),
                )
                os.environ[key] = text
                updated[key] = text
        return updated

    def snapshot(self) -> dict[str, Any]:
        """Public settings for UI (no secrets)."""
        out: dict[str, Any] = {}
        for key in EDITABLE_KEYS:
            out[key] = self.get(key, "")
        # Read-only hints
        out["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME", "")
        out["MAIL_SMTP_HOST"] = os.getenv("MAIL_SMTP_HOST", "")
        out["BITRIX_PORTAL_URL"] = os.getenv("BITRIX_PORTAL_URL", "")
        out["BITRIX_WEBHOOK_CONFIGURED"] = bool(
            (os.getenv("BITRIX_WEBHOOK_URL") or "").strip()
        )
        out["IMAP_CONFIGURED"] = bool(
            (os.getenv("MAIL_USERNAME") or "").strip()
            and (os.getenv("MAIL_PASSWORD") or "")
            and (os.getenv("IMAP_HOST") or "imap.mail.ru")
        )
        out["DADATA_CONFIGURED"] = bool((os.getenv("DADATA_API_KEY") or "").strip())
        return out
