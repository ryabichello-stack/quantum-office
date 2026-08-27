"""Human-readable explanation why today's outreach send count looks “short”."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional


def _cfg_int(settings: Any, key: str, default: int) -> int:
    if settings is None:
        return default
    try:
        if hasattr(settings, "get_int"):
            return int(settings.get_int(key, default))
    except Exception:
        pass
    try:
        if hasattr(settings, "get"):
            return int(settings.get(key, default) or default)
    except Exception:
        pass
    return default


def _human_smtp_error(raw: str) -> str:
    s = (raw or "").strip()
    low = s.lower()
    if "550" in s and "non-local recipient" in low:
        return "SMTP 550: сервер получателя отклонил адрес (non-local recipient verification failed)"
    if "550" in s:
        return f"SMTP 550: {s[:160]}"
    if "421" in s or "452" in s:
        return f"Временный отказ SMTP: {s[:160]}"
    return s[:200] if s else "неизвестная ошибка"


def _fmt_ru_date(iso_day: str) -> str:
    """2026-08-28 → 28.08.2026"""
    try:
        y, m, d = iso_day.split("-")
        return f"{d}.{m}.{y}"
    except Exception:
        return iso_day


def build_send_explain(
    outbox: Any,
    settings: Any = None,
    *,
    daily_limit: Optional[int] = None,
    effective_daily_limit: Optional[int] = None,
) -> dict[str, Any]:
    """Explain remaining daily slots vs scheduled not_before / SMTP failures."""
    daily = int(
        effective_daily_limit
        if effective_daily_limit is not None
        else daily_limit
        if daily_limit is not None
        else _cfg_int(settings, "OUTREACH_DAILY_LIMIT", 15)
    )
    configured = int(daily_limit if daily_limit is not None else _cfg_int(settings, "OUTREACH_DAILY_LIMIT", 15))

    sent_today = 0
    try:
        sent_today = int(outbox.sent_today_count() or 0)
    except Exception:
        sent_today = 0
    remaining = max(0, daily - sent_today)

    due_now = 0
    next_day = ""
    next_count = 0
    failed_rows: list[dict[str, str]] = []
    try:
        with outbox.connect() as conn:
            now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
            due_now = int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM outbox
                    WHERE status = 'pending'
                      AND (not_before IS NULL OR not_before = '' OR not_before <= ?)
                    """,
                    (now,),
                ).fetchone()[0]
            )
            row = conn.execute(
                """
                SELECT date(not_before) AS d, COUNT(*) AS c
                FROM outbox
                WHERE status = 'pending'
                  AND not_before IS NOT NULL AND not_before != ''
                  AND date(not_before) > date('now')
                GROUP BY date(not_before)
                ORDER BY d ASC
                LIMIT 1
                """
            ).fetchone()
            if row:
                next_day = str(row[0] or "")
                next_count = int(row[1] or 0)
            for fr in conn.execute(
                """
                SELECT email, last_error, updated_at
                FROM outbox
                WHERE status = 'failed'
                ORDER BY updated_at DESC
                LIMIT 5
                """
            ):
                failed_rows.append(
                    {
                        "email": str(fr[0] or ""),
                        "error": _human_smtp_error(str(fr[1] or "")),
                        "updated_at": str(fr[2] or ""),
                    }
                )
    except Exception:
        pass

    lines: list[str] = []
    code = "ok"

    if remaining > 0 and due_now == 0 and next_day:
        code = "scheduled_ahead"
        lines.append(
            f"Сегодня ушло {sent_today} из {daily}. Ещё {remaining} слотов свободны, "
            f"но следующие письма уже стоят на {_fmt_ru_date(next_day)} "
            f"({next_count} шт.) — это не сбой отправки."
        )
    elif remaining > 0 and due_now == 0 and not next_day:
        code = "queue_empty"
        lines.append(
            f"Сегодня ушло {sent_today} из {daily}. Свободно {remaining}, "
            "но в очереди нет писем, готовых к отправке."
        )
    elif remaining == 0:
        code = "limit_reached"
        lines.append(f"Дневной лимит исчерпан: {sent_today}/{daily}. Остальные ждут завтра.")
    elif due_now > 0:
        code = "in_progress"
        lines.append(
            f"Сегодня {sent_today}/{daily}. Готовы к отправке сейчас: {due_now} "
            "(с учётом окон и паузы 10–15 мин)."
        )
    else:
        lines.append(f"Сегодня {sent_today}/{daily}, осталось {remaining}.")

    if configured != daily:
        lines.append(f"Эффективный лимит {daily} (настройка {configured}).")

    for fr in failed_rows[:3]:
        lines.append(f"Не доставлено (SMTP): {fr['email']} — {fr['error']}")
        code = "has_failures" if code == "ok" else code

    text = " ".join(lines) if len(lines) == 1 else "\n".join(lines)
    return {
        "ok": True,
        "code": code,
        "sent_today": sent_today,
        "daily_limit": daily,
        "configured_daily_limit": configured,
        "remaining_today": remaining,
        "due_now": due_now,
        "next_scheduled_day": next_day or None,
        "next_scheduled_count": next_count,
        "failed": failed_rows,
        "lines": lines,
        "text": text,
        "title": "Почему не все письма ушли сегодня",
    }
