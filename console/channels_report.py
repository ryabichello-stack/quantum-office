"""Cross-channel engagement report for Quantum Console.

Aggregates messengers (text-bot), email outreach, voice calls, and Tilda form leads
for a selected period. Website visits can later come from Yandex Metrika; Tilda forms
arrive via webhook into a local SQLite store.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("quantum-console.channels")

TEXT_BOT_SESSIONS_DB = Path(
    os.getenv("TEXT_BOT_SESSIONS_DB", "/opt/ava-text-bot/data/sessions.db")
)
OUTREACH_MODULES_DB = Path(
    os.getenv("OUTREACH_MODULES_DB", "/opt/ava-outreach/data/modules.db")
)
OUTREACH_OUTBOX_DB = Path(
    os.getenv("OUTREACH_OUTBOX_DB", "/opt/ava-outreach/data/outbox.db")
)
CALL_HISTORY_DB = Path(
    os.getenv("CALL_HISTORY_DB", "/root/ava/data/call_history.db")
)
CONSOLE_DATA_DIR = Path(
    os.getenv("CONSOLE_DATA_DIR", "/opt/quantum-console/data")
)
TILDA_LEADS_DB = Path(
    os.getenv("TILDA_LEADS_DB", str(CONSOLE_DATA_DIR / "tilda_leads.db"))
)

# Contexts treated as outbound AI dials (rest ≈ inbound / pilots on inbound trunk).
_OUTBOUND_CONTEXTS = frozenset(
    {
        "outbound",
        "demo_outbound",
        "sheets_campaign",
        "campaign",
    }
)


def _parse_day(value: str | None, *, default: date) -> date:
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise ValueError(f"bad date: {raw}") from exc


def resolve_period(
    from_day: str | None = None,
    to_day: str | None = None,
    *,
    default_days: int = 30,
) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    end = _parse_day(to_day, default=today)
    start = _parse_day(from_day, default=end - timedelta(days=max(1, default_days) - 1))
    if start > end:
        start, end = end, start
    return start, end


def _connect(path: Path) -> sqlite3.Connection | None:
    if not path.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as exc:
        logger.warning("cannot open %s: %s", path, exc)
        return None


def _day_in_sql(column: str) -> str:
    # created_at / start_time may be ISO with T or space; take first 10 chars.
    return f"substr(replace({column}, ' ', 'T'), 1, 10)"


def _ensure_tilda_db() -> Path:
    CONSOLE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = TILDA_LEADS_DB
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tilda_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                formid TEXT,
                tranid TEXT,
                name TEXT,
                phone TEXT,
                email TEXT,
                page TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_tilda_leads_created ON tilda_leads(created_at)"
        )
        conn.commit()
    finally:
        conn.close()
    return path


def store_tilda_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a Tilda webhook / forms payload."""
    path = _ensure_tilda_db()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    # Tilda sends flat fields + nested; keep common ones handy.
    formid = str(payload.get("formid") or payload.get("formname") or "")[:120]
    tranid = str(payload.get("tranid") or payload.get("Id") or "")[:120]
    name = str(
        payload.get("Name")
        or payload.get("name")
        or payload.get("Имя")
        or ""
    )[:200]
    phone = str(
        payload.get("Phone")
        or payload.get("phone")
        or payload.get("Телефон")
        or ""
    )[:80]
    email = str(
        payload.get("Email")
        or payload.get("email")
        or payload.get("Почта")
        or ""
    )[:200]
    page = str(payload.get("page") or payload.get("referer") or "")[:400]
    conn = sqlite3.connect(path)
    try:
        cur = conn.execute(
            """
            INSERT INTO tilda_leads
              (formid, tranid, name, phone, email, page, payload_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                formid,
                tranid,
                name,
                phone,
                email,
                page,
                json.dumps(payload, ensure_ascii=False)[:20000],
                now,
            ),
        )
        conn.commit()
        return {"ok": True, "id": cur.lastrowid, "created_at": now}
    finally:
        conn.close()


def _messengers_stats(start: date, end: date) -> dict[str, Any]:
    empty = {
        "available": False,
        "channels": {},
        "totals": {
            "sessions": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "new_chats": 0,
        },
    }
    conn = _connect(TEXT_BOT_SESSIONS_DB)
    if not conn:
        return empty
    try:
        # New chats ≈ first user message in period (or session_meta.updated_at if no messages).
        channels: dict[str, dict[str, int]] = {}
        rows = conn.execute(
            f"""
            SELECT
              CASE
                WHEN chat_id LIKE 'telegram_business:%' THEN 'telegram_business'
                WHEN chat_id LIKE 'telegram:%' THEN 'telegram'
                WHEN chat_id LIKE 'max:%' THEN 'max'
                WHEN chat_id LIKE 'whatsapp:%' THEN 'whatsapp'
                WHEN chat_id LIKE 'vk:%' THEN 'vk'
                WHEN chat_id LIKE 'api:%' THEN 'api'
                WHEN chat_id LIKE 'web:%' THEN 'web'
                ELSE 'other'
              END AS channel,
              role,
              COUNT(*) AS n
            FROM chat_messages
            WHERE {_day_in_sql('created_at')} BETWEEN ? AND ?
              AND chat_id NOT LIKE '%smoke%'
              AND chat_id NOT LIKE 'api:e2e%'
              AND chat_id NOT LIKE 'api:guest%'
              AND chat_id NOT LIKE 'api:deploy%'
              AND chat_id NOT LIKE 'owner:smoke%'
            GROUP BY channel, role
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for r in rows:
            ch = r["channel"]
            bucket = channels.setdefault(
                ch,
                {
                    "user_messages": 0,
                    "assistant_messages": 0,
                    "tool_messages": 0,
                    "new_chats": 0,
                },
            )
            role = (r["role"] or "").lower()
            if role == "user":
                bucket["user_messages"] += int(r["n"])
            elif role == "assistant":
                bucket["assistant_messages"] += int(r["n"])
            else:
                bucket["tool_messages"] += int(r["n"])

        chat_rows = conn.execute(
            f"""
            SELECT
              CASE
                WHEN chat_id LIKE 'telegram_business:%' THEN 'telegram_business'
                WHEN chat_id LIKE 'telegram:%' THEN 'telegram'
                WHEN chat_id LIKE 'max:%' THEN 'max'
                WHEN chat_id LIKE 'whatsapp:%' THEN 'whatsapp'
                WHEN chat_id LIKE 'vk:%' THEN 'vk'
                WHEN chat_id LIKE 'api:%' THEN 'api'
                WHEN chat_id LIKE 'web:%' THEN 'web'
                ELSE 'other'
              END AS channel,
              COUNT(DISTINCT chat_id) AS n
            FROM chat_messages
            WHERE role = 'user'
              AND {_day_in_sql('created_at')} BETWEEN ? AND ?
              AND chat_id NOT LIKE '%smoke%'
              AND chat_id NOT LIKE 'api:e2e%'
              AND chat_id NOT LIKE 'api:guest%'
              AND chat_id NOT LIKE 'api:deploy%'
            GROUP BY channel
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        for r in chat_rows:
            ch = r["channel"]
            channels.setdefault(
                ch,
                {
                    "user_messages": 0,
                    "assistant_messages": 0,
                    "tool_messages": 0,
                    "new_chats": 0,
                },
            )["new_chats"] = int(r["n"])

        totals = {
            "sessions": sum(v.get("new_chats", 0) for v in channels.values()),
            "user_messages": sum(v.get("user_messages", 0) for v in channels.values()),
            "assistant_messages": sum(
                v.get("assistant_messages", 0) for v in channels.values()
            ),
            "new_chats": sum(v.get("new_chats", 0) for v in channels.values()),
        }
        # Friendly aliases for UI
        telegram = {
            "new_chats": channels.get("telegram", {}).get("new_chats", 0)
            + channels.get("telegram_business", {}).get("new_chats", 0),
            "user_messages": channels.get("telegram", {}).get("user_messages", 0)
            + channels.get("telegram_business", {}).get("user_messages", 0),
            "assistant_messages": channels.get("telegram", {}).get(
                "assistant_messages", 0
            )
            + channels.get("telegram_business", {}).get("assistant_messages", 0),
        }
        max_ch = channels.get("max") or {
            "new_chats": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_messages": 0,
        }
        return {
            "available": True,
            "channels": channels,
            "telegram": telegram,
            "max": max_ch,
            "totals": totals,
        }
    except sqlite3.Error as exc:
        logger.warning("messengers stats failed: %s", exc)
        return empty
    finally:
        conn.close()


def _email_stats(start: date, end: date) -> dict[str, Any]:
    empty = {
        "available": False,
        "sent": 0,
        "unique_recipients": 0,
        "delivered": 0,
        "opened": 0,
        "open_events": 0,
        "bounced": 0,
        "replied": 0,
        "unsubscribed": 0,
        "pending_queue": None,
        "by_day": [],
        "notes": {
            "delivered": "sent − hard bounce (нет webhook доставки Mail.ru)",
            "opened": "HTML open-pixel; клиенты с блокировкой картинок занижают",
            "external_only": "без @quantumlabs.ru",
        },
    }
    conn = _connect(OUTREACH_MODULES_DB)
    if not conn:
        return empty
    try:
        excl = "email NOT LIKE '%@quantumlabs.ru'"
        day_col = _day_in_sql("created_at")
        base = f"FROM send_events WHERE {excl} AND {day_col} BETWEEN ? AND ?"
        args = (start.isoformat(), end.isoformat())
        sent = conn.execute(f"SELECT COUNT(*) c {base}", args).fetchone()["c"]
        uniq = conn.execute(
            f"SELECT COUNT(DISTINCT email) c {base}", args
        ).fetchone()["c"]
        opened = conn.execute(
            f"SELECT COUNT(*) c {base} AND (opened_at IS NOT NULL OR open_count > 0)",
            args,
        ).fetchone()["c"]
        open_events = (
            conn.execute(
                f"SELECT COALESCE(SUM(open_count), 0) c {base}", args
            ).fetchone()["c"]
            or 0
        )
        bounced = conn.execute(
            f"SELECT COUNT(*) c {base} AND bounced_at IS NOT NULL", args
        ).fetchone()["c"]
        replied = conn.execute(
            f"SELECT COUNT(*) c {base} AND replied_at IS NOT NULL", args
        ).fetchone()["c"]
        unsub = 0
        try:
            unsub = conn.execute(
                f"""
                SELECT COUNT(*) c FROM suppression
                WHERE reason = 'unsubscribe'
                  AND {_day_in_sql('created_at')} BETWEEN ? AND ?
                """,
                args,
            ).fetchone()["c"]
        except sqlite3.Error:
            unsub = 0
        by_day = [
            {
                "day": r["d"],
                "sent": r["n"],
                "opened": r["op"],
                "bounced": r["bo"],
            }
            for r in conn.execute(
                f"""
                SELECT {day_col} AS d, COUNT(*) n,
                  SUM(CASE WHEN opened_at IS NOT NULL OR open_count > 0 THEN 1 ELSE 0 END) op,
                  SUM(CASE WHEN bounced_at IS NOT NULL THEN 1 ELSE 0 END) bo
                {base}
                GROUP BY d ORDER BY d
                """,
                args,
            )
        ]
        pending = None
        out = _connect(OUTREACH_OUTBOX_DB)
        if out:
            try:
                pending = out.execute(
                    "SELECT COUNT(*) c FROM outbox WHERE status = 'pending'"
                ).fetchone()["c"]
            finally:
                out.close()
        delivered = max(0, int(sent) - int(bounced))
        return {
            "available": True,
            "sent": int(sent),
            "unique_recipients": int(uniq),
            "delivered": delivered,
            "opened": int(opened),
            "open_events": int(open_events),
            "bounced": int(bounced),
            "replied": int(replied),
            "unsubscribed": int(unsub),
            "pending_queue": pending,
            "by_day": by_day,
            "notes": empty["notes"],
        }
    except sqlite3.Error as exc:
        logger.warning("email stats failed: %s", exc)
        return empty
    finally:
        conn.close()


def _calls_stats(start: date, end: date) -> dict[str, Any]:
    empty = {
        "available": False,
        "inbound": {"count": 0, "completed": 0, "avg_duration_sec": None},
        "outbound": {"count": 0, "completed": 0, "avg_duration_sec": None},
        "other": {"count": 0},
        "total": 0,
        "by_context": [],
    }
    conn = _connect(CALL_HISTORY_DB)
    if not conn:
        return empty
    try:
        day_col = _day_in_sql("start_time")
        rows = conn.execute(
            f"""
            SELECT
              COALESCE(NULLIF(context_name, ''), '(blank)') AS ctx,
              COUNT(*) AS n,
              SUM(CASE WHEN outcome = 'completed' THEN 1 ELSE 0 END) AS completed,
              AVG(duration_seconds) AS avg_dur
            FROM call_records
            WHERE {day_col} BETWEEN ? AND ?
            GROUP BY ctx
            ORDER BY n DESC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        inbound = {
            "count": 0,
            "completed": 0,
            "avg_duration_sec": None,
            "_dur_sum": 0.0,
            "_dur_n": 0,
        }
        outbound = {
            "count": 0,
            "completed": 0,
            "avg_duration_sec": None,
            "_dur_sum": 0.0,
            "_dur_n": 0,
        }
        other = {"count": 0, "completed": 0}
        by_context = []
        for r in rows:
            ctx = r["ctx"]
            item = {
                "context": ctx,
                "count": int(r["n"]),
                "completed": int(r["completed"] or 0),
                "avg_duration_sec": round(float(r["avg_dur"]), 1)
                if r["avg_dur"] is not None
                else None,
            }
            by_context.append(item)
            if ctx in _OUTBOUND_CONTEXTS:
                bucket = outbound
            elif ctx.startswith("demo_") and ctx != "demo_outbound":
                other["count"] += item["count"]
                other["completed"] += item["completed"]
                continue
            else:
                # default / blank / cartesia_pilot / telephony_ulaw — входящая линия
                bucket = inbound
            bucket["count"] += item["count"]
            bucket["completed"] += item["completed"]
            if item["avg_duration_sec"] is not None:
                bucket["_dur_sum"] += item["avg_duration_sec"] * item["count"]
                bucket["_dur_n"] += item["count"]

        def _finish(bucket: dict[str, Any]) -> dict[str, Any]:
            avg = None
            if bucket.get("_dur_n"):
                avg = round(bucket["_dur_sum"] / bucket["_dur_n"], 1)
            return {
                "count": bucket["count"],
                "completed": bucket["completed"],
                "avg_duration_sec": avg,
            }

        return {
            "available": True,
            "inbound": _finish(inbound),
            "outbound": _finish(outbound),
            "other": {"count": other["count"], "completed": other.get("completed", 0)},
            "total": sum(i["count"] for i in by_context),
            "by_context": by_context,
        }
    except sqlite3.Error as exc:
        logger.warning("calls stats failed: %s", exc)
        return empty
    finally:
        conn.close()


def _tilda_stats(start: date, end: date) -> dict[str, Any]:
    empty = {
        "available": False,
        "leads": 0,
        "visits": None,
        "conversion_pct": None,
        "by_day": [],
        "recent": [],
        "notes": {
            "leads": "Webhook форм Tilda → POST /api/channels/tilda/lead",
            "visits": "Подключите Yandex Metrika (TILDA_METRIKA_COUNTER + OAuth) или вручную",
        },
    }
    path = TILDA_LEADS_DB
    if not path.is_file():
        try:
            _ensure_tilda_db()
        except OSError:
            return empty
    conn = _connect(path)
    if not conn:
        # writable ensure may have created empty DB — try again
        try:
            _ensure_tilda_db()
            conn = _connect(path)
        except OSError:
            return empty
    if not conn:
        return empty
    try:
        day_col = _day_in_sql("created_at")
        leads = conn.execute(
            f"SELECT COUNT(*) c FROM tilda_leads WHERE {day_col} BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()["c"]
        by_day = [
            {"day": r["d"], "leads": r["n"]}
            for r in conn.execute(
                f"""
                SELECT {day_col} AS d, COUNT(*) n
                FROM tilda_leads
                WHERE {day_col} BETWEEN ? AND ?
                GROUP BY d ORDER BY d
                """,
                (start.isoformat(), end.isoformat()),
            )
        ]
        recent = [
            dict(r)
            for r in conn.execute(
                f"""
                SELECT id, formid, name, phone, email, page, created_at
                FROM tilda_leads
                WHERE {day_col} BETWEEN ? AND ?
                ORDER BY created_at DESC LIMIT 20
                """,
                (start.isoformat(), end.isoformat()),
            )
        ]
        visits = _metrika_visits(start, end)
        conversion = None
        if visits is not None and visits > 0:
            conversion = round(100.0 * int(leads) / visits, 2)
        return {
            "available": True,
            "leads": int(leads),
            "visits": visits,
            "conversion_pct": conversion,
            "by_day": by_day,
            "recent": recent,
            "notes": empty["notes"],
        }
    except sqlite3.Error as exc:
        logger.warning("tilda stats failed: %s", exc)
        return empty
    finally:
        conn.close()


def _metrika_visits(start: date, end: date) -> int | None:
    """Optional Yandex Metrika visits for the site (Tilda-hosted or custom domain)."""
    counter = (os.getenv("TILDA_METRIKA_COUNTER") or os.getenv("METRIKA_COUNTER_ID") or "").strip()
    token = (os.getenv("TILDA_METRIKA_TOKEN") or os.getenv("METRIKA_OAUTH_TOKEN") or "").strip()
    if not counter or not token:
        return None
    # Management API: https://api-metrika.yandex.net/stat/v1/data
    url = (
        "https://api-metrika.yandex.net/stat/v1/data"
        f"?ids={urllib_quote(counter)}"
        f"&metrics=ym:s:visits"
        f"&date1={start.isoformat()}"
        f"&date2={end.isoformat()}"
    )
    try:
        req = Request(url, headers={"Authorization": f"OAuth {token}"})
        with urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        totals = data.get("totals") or []
        if totals:
            return int(float(totals[0]))
    except (URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
        logger.warning("metrika visits failed: %s", exc)
    return None


def urllib_quote(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value), safe="")


def build_channels_report(
    *,
    from_day: str | None = None,
    to_day: str | None = None,
    default_days: int = 30,
) -> dict[str, Any]:
    start, end = resolve_period(from_day, to_day, default_days=default_days)
    messengers = _messengers_stats(start, end)
    email = _email_stats(start, end)
    calls = _calls_stats(start, end)
    tilda = _tilda_stats(start, end)

    summary = {
        "telegram_chats": (messengers.get("telegram") or {}).get("new_chats", 0),
        "telegram_messages": (messengers.get("telegram") or {}).get("user_messages", 0),
        "max_chats": (messengers.get("max") or {}).get("new_chats", 0),
        "max_messages": (messengers.get("max") or {}).get("user_messages", 0),
        "email_sent": email.get("sent", 0),
        "email_opened": email.get("opened", 0),
        "email_replied": email.get("replied", 0),
        "calls_inbound": (calls.get("inbound") or {}).get("count", 0),
        "calls_outbound": (calls.get("outbound") or {}).get("count", 0),
        "tilda_leads": tilda.get("leads", 0),
        "tilda_visits": tilda.get("visits"),
    }

    return {
        "ok": True,
        "period": {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": (end - start).days + 1,
        },
        "summary": summary,
        "messengers": messengers,
        "email": email,
        "calls": calls,
        "tilda": tilda,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
