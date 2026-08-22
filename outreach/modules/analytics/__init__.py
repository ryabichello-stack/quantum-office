"""Engagement analytics: funnel, rates, daily series for outreach report UI."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from core.paths import OUTBOX_DB
from core.registry import AppContext
from modules.tracking import TrackingStore, open_tracking_enabled, tracking_public_base
from outbox import OutboxStore

logger = logging.getLogger("ava-outreach.analytics")


def _pct(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    return round(100.0 * num / den, 2)


def build_sequence_step_report(seq_store: Any, *, max_steps: int = 5) -> dict[str, Any]:
    """Funnel by sequence step reached (current_step = last completed send)."""
    steps_out: list[dict[str, Any]] = []
    status_counts: dict[str, int] = {}
    total = 0
    with seq_store.connect() as conn:
        total = int(conn.execute("SELECT COUNT(*) AS n FROM sequence_leads").fetchone()["n"])
        for row in conn.execute(
            "SELECT status, COUNT(*) AS n FROM sequence_leads GROUP BY status"
        ):
            status_counts[str(row["status"])] = int(row["n"])
        for step in range(1, max(1, max_steps) + 1):
            reached = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM sequence_leads WHERE current_step >= ?",
                    (step,),
                ).fetchone()["n"]
            )
            steps_out.append(
                {
                    "step": step,
                    "reached": reached,
                    "pct_of_total": round(100.0 * reached / total, 1) if total else None,
                }
            )
    return {
        "total_sequences": total,
        "status_counts": status_counts,
        "steps": steps_out,
        "notes": {
            "reached": "current_step >= N — получили как минимум N-е письмо цепочки",
        },
    }


def build_report(
    *,
    tracking: TrackingStore,
    outbox: OutboxStore,
    days: int = 14,
    recent_limit: int = 40,
    settings: Any = None,
) -> dict[str, Any]:
    counts = tracking.engagement_counts()
    out_counts = outbox.status_report().get("counts") or {}
    queued = int(out_counts.get("pending") or 0)
    failed = int(out_counts.get("failed") or 0)

    funnel = {
        "queued": queued,
        "sent": counts["sent"],
        "delivered": counts["delivered"],
        "not_delivered": counts["not_delivered"],
        "opened": counts["opened"],
        "not_opened": counts["not_opened"],
        "replied": counts["replied"],
        "bounced": counts["bounced"],
        "failed": failed,
        "notes": {
            "delivered": "inferred: sent − bounced (no Mail.ru delivery webhook)",
            "opened": "HTML tracking pixel; image-blocked clients undercount opens",
            "not_delivered": "IMAP bounce / DSN matched to Message-ID",
            "spam": "high bounce or near-zero open rate → check content/warmup/domain reputation",
        },
    }
    rates = {
        "delivery_rate_pct": _pct(funnel["delivered"], funnel["sent"]),
        "bounce_rate_pct": _pct(funnel["bounced"], funnel["sent"]),
        "open_rate_pct": _pct(funnel["opened"], funnel["delivered"] or funnel["sent"]),
        "open_rate_of_sent_pct": _pct(funnel["opened"], funnel["sent"]),
        "reply_rate_pct": _pct(funnel["replied"], funnel["delivered"] or funnel["sent"]),
        "reply_of_opened_pct": _pct(funnel["replied"], funnel["opened"]),
        "fail_rate_pct": _pct(failed, funnel["sent"] + failed + queued),
    }

    recent_items = []
    for ev in tracking.recent(limit=max(1, min(200, recent_limit))):
        if ev.replied_at:
            eng = "replied"
        elif ev.bounced_at:
            eng = "bounced"
        elif ev.opened_at:
            eng = "opened"
        else:
            eng = "sent"
        recent_items.append(
            {
                **ev.to_dict(),
                "engagement": eng,
                # never expose open_token in UI report
                "open_token": None,
            }
        )

    return {
        "ok": True,
        "funnel": funnel,
        "rates": rates,
        "daily": tracking.daily_series(days),
        "recent": recent_items,
        "open_tracking": open_tracking_enabled(settings),
        "tracking_public_base": tracking_public_base(settings),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def build_report_with_sequences(
    *,
    tracking: TrackingStore,
    outbox: OutboxStore,
    seq_store: Any,
    days: int = 14,
    recent_limit: int = 40,
    settings: Any = None,
) -> dict[str, Any]:
    report = build_report(
        tracking=tracking,
        outbox=outbox,
        days=days,
        recent_limit=recent_limit,
        settings=settings,
    )
    report["sequence_steps"] = build_sequence_step_report(seq_store)
    return report


class AnalyticsModule:
    name = "analytics"
    version = "1.1.0"

    def __init__(self) -> None:
        self.tracking = TrackingStore()
        self._settings: Any = None
        self._sequences: Any = None

    def init_db(self) -> None:
        self.tracking.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        self._settings = ctx.settings
        if "tracking" in ctx.extras:
            self.tracking = ctx.extras["tracking"]
        if "sequences" in ctx.extras:
            self._sequences = ctx.extras["sequences"]
        ctx.extras["analytics"] = self
        logger.info("analytics module ready")

    def on_shutdown(self) -> None:
        return None

    def health(self) -> dict[str, Any]:
        c = self.tracking.engagement_counts()
        return {
            "ok": True,
            "sent": c["sent"],
            "delivered": c["delivered"],
            "opened": c["opened"],
            "replied": c["replied"],
            "bounced": c["bounced"],
        }

    def register_routes(self, router: Any) -> None:
        from fastapi import Query

        @router.get("/report")
        def api_report(
            days: int = Query(14, ge=1, le=90),
            recent_limit: int = Query(40, ge=1, le=200),
        ) -> dict[str, Any]:
            from modules.sequences import SequenceStore

            seq = self._sequences or SequenceStore()
            return build_report_with_sequences(
                tracking=self.tracking,
                outbox=OutboxStore(OUTBOX_DB),
                seq_store=seq,
                days=days,
                recent_limit=recent_limit,
                settings=self._settings,
            )

        @router.get("/sequence-steps")
        def api_sequence_steps() -> dict[str, Any]:
            from modules.sequences import SequenceStore

            seq = self._sequences or SequenceStore()
            return {"ok": True, **build_sequence_step_report(seq)}

        @router.get("/funnel")
        def api_funnel() -> dict[str, Any]:
            return build_report(
                tracking=self.tracking,
                outbox=OutboxStore(OUTBOX_DB),
                days=7,
                recent_limit=5,
                settings=self._settings,
            )["funnel"]
