"""Operator control plane: alerts + next-action queue for the outreach UI."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

_ACTIONABLE_INBOX = frozenset(
    {
        "positive_interest",
        "human_unclassified",
        "forwarded",
        "negative",
        "unsubscribe",
        "unknown",
    }
)
_INBOX_SEVERITY = {
    "positive_interest": "high",
    "human_unclassified": "high",
    "forwarded": "high",
    "negative": "medium",
    "unsubscribe": "medium",
    "unknown": "medium",
    "out_of_office": "low",
    "automatic": "low",
    "bounce": "low",
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def build_ops_summary(
    *,
    rt: Any,
    deliverability: Any,
    reply_inbox: Any,
    sequences: Any,
    runner: Any,
    reply_watch: dict[str, Any] | None = None,
    callback_requests: list[dict[str, Any]] | None = None,
    queue: dict[str, Any] | None = None,
    outbox_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate operator alerts and prioritized next actions."""
    now = _utc_now()
    alerts: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    paused, pause_reason = deliverability.is_paused()
    if paused:
        alerts.append(
            {
                "id": "mailbox_paused",
                "level": "critical",
                "title": "Ящик на паузе (deliverability)",
                "detail": pause_reason or "bounce spike / manual pause",
                "tab": "settings",
            }
        )
        actions.append(
            {
                "id": "act-mailbox-paused",
                "kind": "mailbox_paused",
                "severity": "high",
                "title": "Снять паузу ящика",
                "detail": pause_reason or "Anti-ban → Resume",
                "tab": "settings",
            }
        )

    reply_watch = reply_watch or {}
    watch_enabled = rt.get_bool("REPLY_WATCH_ENABLED", True)
    imap_ok = bool(reply_watch.get("imap_configured"))
    if watch_enabled and not imap_ok:
        alerts.append(
            {
                "id": "imap_missing",
                "level": "warning",
                "title": "IMAP не настроен",
                "detail": "Ответы не отслеживаются — проверьте MAIL_* в .env",
                "tab": "settings",
            }
        )
    elif watch_enabled and imap_ok:
        last_at = _parse_iso(reply_watch.get("last_at"))
        interval = int(reply_watch.get("interval_seconds") or 120)
        if reply_watch.get("last_error"):
            alerts.append(
                {
                    "id": "reply_watch_error",
                    "level": "warning",
                    "title": "Ошибка IMAP watcher",
                    "detail": str(reply_watch.get("last_error"))[:240],
                    "tab": "inbox",
                }
            )
        elif last_at is None:
            alerts.append(
                {
                    "id": "reply_watch_stale",
                    "level": "info",
                    "title": "IMAP watcher ещё не опрашивал почту",
                    "detail": "Подождите первый цикл или нажмите «Проверить ответы»",
                    "tab": "inbox",
                }
            )
        elif (now - last_at) > timedelta(seconds=max(180, interval * 2)):
            alerts.append(
                {
                    "id": "reply_watch_stale",
                    "level": "warning",
                    "title": "IMAP watcher давно не отвечал",
                    "detail": f"Последний цикл: {last_at.isoformat()}",
                    "tab": "inbox",
                }
            )

    run_state = (rt.get("OUTREACH_RUN_STATE", "stopped") or "stopped").lower()
    pending = int((outbox_counts or {}).get("pending") or 0)
    due_n = int((queue or {}).get("due") or 0)
    if run_state == "stopped" and (pending > 0 or due_n > 0):
        alerts.append(
            {
                "id": "runner_stopped",
                "level": "info",
                "title": "Рассылка остановлена",
                "detail": f"В очереди: {pending} первых, {due_n} due follow-up",
                "tab": "outbox",
            }
        )

    # Playing but nobody in local B2B slots → looks like "Start broken"
    in_window_n = int((queue or {}).get("first_touch_in_window") or 0)
    slots = (rt.get("SCHEDULE_SLOTS", "") or "10:00-11:30,14:30-16:30").strip()
    if run_state == "playing" and pending > 0 and in_window_n <= 0:
        alerts.append(
            {
                "id": "outside_send_window",
                "level": "warning",
                "title": "Старт включён, но сейчас вне окон отправки",
                "detail": (
                    f"В окне сейчас: 0 из {pending}. Слоты (локальное время получателя): {slots}. "
                    "Письма уйдут в следующий слот — в «Отправленные» пока пусто."
                ),
                "tab": "outbox",
            }
        )
        actions.insert(
            0,
            {
                "id": "act-outside-window",
                "kind": "outside_window",
                "severity": "high",
                "title": "Ждём локальное окно (или расширьте слоты в Настройках)",
                "detail": f"Сейчас 0 контактов в окне · слоты {slots}",
                "tab": "settings",
            },
        )

    seq_counts = sequences.counts() if hasattr(sequences, "counts") else {}
    paused_seq = int(seq_counts.get("paused") or 0)
    if paused_seq:
        actions.append(
            {
                "id": "act-seq-paused",
                "kind": "sequences_paused",
                "severity": "low",
                "title": f"Цепочки на паузе (OOO): {paused_seq}",
                "detail": "Проверьте входящие / возобновятся по сроку",
                "tab": "inbox",
                "count": paused_seq,
            }
        )

    if due_n and run_state == "playing":
        actions.append(
            {
                "id": "act-due-followups",
                "kind": "due_followups",
                "severity": "medium",
                "title": f"Due follow-up: {due_n}",
                "detail": "Смотрите вкладку Очередь",
                "tab": "outbox",
                "count": due_n,
            }
        )

    inbox_items = reply_inbox.list_unprocessed(15) if hasattr(reply_inbox, "list_unprocessed") else []
    for row in inbox_items:
        cls = str(row.get("classification") or "unknown")
        if cls not in _ACTIONABLE_INBOX and cls not in ("out_of_office", "automatic"):
            continue
        rid = row.get("id")
        actions.append(
            {
                "id": f"inbox-{rid}",
                "kind": "inbox_reply",
                "severity": _INBOX_SEVERITY.get(cls, "medium"),
                "title": f"Входящее: {cls}",
                "detail": f"{row.get('from_email') or '—'} — {(row.get('subject') or '')[:80]}",
                "tab": "inbox",
                "inbox_id": rid,
                "classification": cls,
                "created_at": row.get("created_at"),
            }
        )

    callback_requests = callback_requests or []
    cutoff = now - timedelta(hours=48)
    for cb in callback_requests[:10]:
        created = _parse_iso(str(cb.get("created_at") or ""))
        if created and created < cutoff:
            continue
        actions.append(
            {
                "id": f"callback-{cb.get('id')}",
                "kind": "callback",
                "severity": "high",
                "title": "Заявка на звонок (email CTA)",
                "detail": f"{cb.get('fio') or '—'} · {cb.get('phone') or '—'}",
                "tab": "inbox",
                "created_at": cb.get("created_at"),
            }
        )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: (severity_order.get(a.get("severity"), 9), a.get("created_at") or ""))

    level_order = {"critical": 0, "warning": 1, "info": 2}
    alerts.sort(key=lambda a: level_order.get(a.get("level"), 9))

    return {
        "ok": True,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "alerts": alerts,
        "actions": actions[:20],
        "counts": {
            "alerts": len(alerts),
            "actions": len(actions),
            "inbox_unprocessed": int((reply_inbox.counts() or {}).get("unprocessed", 0))
            if hasattr(reply_inbox, "counts")
            else len(inbox_items),
            "sequences_paused": paused_seq,
            "due_followups": due_n,
            "mailbox_paused": bool(paused),
        },
    }
