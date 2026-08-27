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
        prev_reached: int | None = None
        for step in range(1, max(1, max_steps) + 1):
            reached = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM sequence_leads WHERE current_step >= ?",
                    (step,),
                ).fetchone()["n"]
            )
            pct_from_prev = (
                round(100.0 * reached / prev_reached, 1)
                if prev_reached and prev_reached > 0
                else None
            )
            steps_out.append(
                {
                    "step": step,
                    "reached": reached,
                    "pct_of_total": round(100.0 * reached / total, 1) if total else None,
                    "pct_from_prev": pct_from_prev,
                }
            )
            prev_reached = reached
    return {
        "total_sequences": total,
        "status_counts": status_counts,
        "steps": steps_out,
        "notes": {
            "reached": "current_step >= N — получили как минимум N-е письмо цепочки",
        },
    }


def _callback_slice(*, recent_limit: int = 40) -> dict[str, Any]:
    """CTA «Перезвонить» counts + recent form submits."""
    try:
        from callback_cta import recent_requests, requests_count

        total = int(requests_count())
        recent = recent_requests(limit=recent_limit) or []
        dial_ok = sum(1 for x in recent if x.get("dial_ok"))
        return {
            "ok": True,
            "total": total,
            "recent": recent,
            "dial_ok_recent": dial_ok,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("callback slice failed: %s", exc)
        return {"ok": False, "total": 0, "recent": [], "dial_ok_recent": 0, "error": str(exc)[:160]}


def _telephony_slice(*, store: Any = None, recent_limit: int = 40) -> dict[str, Any]:
    """AVA telephony leads ingested into outreach."""
    if store is None:
        try:
            from modules.telephony import TelephonyLeadStore

            store = TelephonyLeadStore()
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "total": 0,
                "ok_count": 0,
                "recent": [],
                "error": str(exc)[:160],
            }
    try:
        counts = store.counts() if hasattr(store, "counts") else {}
        items = store.list_recent(limit=recent_limit) if hasattr(store, "list_recent") else []
        return {
            "ok": True,
            "total": int(counts.get("leads") or 0),
            "ok_count": int(counts.get("ok") or 0),
            "recent": items or [],
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("telephony slice failed: %s", exc)
        return {
            "ok": False,
            "total": 0,
            "ok_count": 0,
            "recent": [],
            "error": str(exc)[:160],
        }


def build_report(
    *,
    tracking: TrackingStore,
    outbox: OutboxStore,
    days: int = 14,
    recent_limit: int = 40,
    settings: Any = None,
    telephony_store: Any = None,
) -> dict[str, Any]:
    counts = tracking.engagement_counts()
    out_counts = outbox.status_report().get("counts") or {}
    queued = int(out_counts.get("pending") or 0)
    failed = int(out_counts.get("failed") or 0)
    cb = _callback_slice(recent_limit=recent_limit)
    tel = _telephony_slice(store=telephony_store, recent_limit=recent_limit)
    callbacks = int(cb.get("total") or 0)
    calls = int(tel.get("total") or 0)

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
        "callbacks": callbacks,
        "calls": calls,
        "calls_ok": int(tel.get("ok_count") or 0),
        "notes": {
            "delivered": "inferred: sent − bounced (no Mail.ru delivery webhook)",
            "opened": "HTML tracking pixel; image-blocked clients undercount opens",
            "not_delivered": "IMAP bounce / DSN matched to Message-ID",
            "callbacks": "кнопка «Перезвонить» в письме → форма → заявка (+ автодозвон)",
            "calls": "входящие/обработанные звонки AVA → telephony_leads",
            "spam": "high bounce or near-zero open rate → check content/warmup/domain reputation",
            "failed": "SMTP-отклонение адреса/сервера. Детали — last_error в Очереди.",
            "queued": "Ждут слот: окна отправки, лимит/день и расписание (not_before).",
        },
    }
    try:
        from send_explain import build_send_explain

        explain = build_send_explain(outbox, settings)
        if explain.get("text"):
            funnel["notes"]["today"] = explain["text"]
            funnel["send_explain"] = explain
    except Exception:
        logger.exception("send_explain failed")
    rates = {
        "delivery_rate_pct": _pct(funnel["delivered"], funnel["sent"]),
        "bounce_rate_pct": _pct(funnel["bounced"], funnel["sent"]),
        "open_rate_pct": _pct(funnel["opened"], funnel["delivered"] or funnel["sent"]),
        "open_rate_of_sent_pct": _pct(funnel["opened"], funnel["sent"]),
        "reply_rate_pct": _pct(funnel["replied"], funnel["delivered"] or funnel["sent"]),
        "reply_of_opened_pct": _pct(funnel["replied"], funnel["opened"]),
        "callback_of_opened_pct": _pct(callbacks, funnel["opened"]),
        "callback_of_sent_pct": _pct(callbacks, funnel["sent"]),
        "call_of_callback_pct": _pct(calls, callbacks) if callbacks else _pct(calls, funnel["sent"]),
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
        "callbacks": cb,
        "calls": tel,
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
    telephony_store: Any = None,
) -> dict[str, Any]:
    report = build_report(
        tracking=tracking,
        outbox=outbox,
        days=days,
        recent_limit=recent_limit,
        settings=settings,
        telephony_store=telephony_store,
    )
    report["sequence_steps"] = build_sequence_step_report(seq_store)
    return report


class AnalyticsModule:
    name = "analytics"
    version = "1.2.0"

    def __init__(self) -> None:
        self.tracking = TrackingStore()
        self._settings: Any = None
        self._sequences: Any = None
        self._telephony_store: Any = None

    def init_db(self) -> None:
        self.tracking.init_db()

    def on_startup(self, ctx: AppContext) -> None:
        self._settings = ctx.settings
        if "tracking" in ctx.extras:
            self.tracking = ctx.extras["tracking"]
        if "sequences" in ctx.extras:
            self._sequences = ctx.extras["sequences"]
        if "telephony" in ctx.extras:
            tel = ctx.extras["telephony"]
            self._telephony_store = getattr(tel, "store", tel)
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
                telephony_store=self._telephony_store,
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
                telephony_store=self._telephony_store,
            )["funnel"]
