"""Quantum Panel Telegram: interactive stats + Mini App.

Uses the same @Quantum_panel_bot token (OPS_NOTIFY_TELEGRAM_*).
Only allowlisted chats (operator chat id) can see stats.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qsl

logger = logging.getLogger("ava-outreach.tg_panel")

BTN_STATS = "📊 Статистика"
BTN_QUEUE = "📬 Очередь"
BTN_HELP = "❓ Помощь"


def _cfg(settings: Any, key: str, default: str = "") -> str:
    if settings is None:
        return (os.getenv(key, default) or default).strip()
    try:
        if hasattr(settings, "get"):
            return str(settings.get(key, default) or default).strip()
    except Exception:  # noqa: BLE001
        pass
    return (os.getenv(key, default) or default).strip()


def _cfg_bool(settings: Any, key: str, default: bool = False) -> bool:
    raw = _cfg(settings, key, "true" if default else "false").lower()
    return raw in ("1", "true", "yes", "on")


def telegram_api(token: str, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = None
    if params:
        data = urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return {"ok": False, "error": f"telegram_http_{exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:300]}
    if not payload.get("ok"):
        return {
            "ok": False,
            "error": payload.get("description") or "telegram_error",
            "raw": payload,
        }
    return {"ok": True, "result": payload.get("result")}


def resolve_bot_token(settings: Any = None) -> str:
    return _cfg(settings, "OPS_NOTIFY_TELEGRAM_BOT_TOKEN", "")


def allowed_chat_ids(settings: Any = None) -> set[str]:
    primary = _cfg(settings, "OPS_NOTIFY_TELEGRAM_CHAT_ID", "")
    extra = _cfg(settings, "OPS_NOTIFY_TELEGRAM_ALLOW_CHATS", "")
    ids: set[str] = set()
    for part in f"{primary},{extra}".split(","):
        p = part.strip()
        if p:
            ids.add(p)
    return ids


def chat_allowed(chat_id: str | int | None, settings: Any = None) -> bool:
    if chat_id is None:
        return False
    allow = allowed_chat_ids(settings)
    if not allow:
        return False
    return str(chat_id).strip() in allow


def public_webapp_url(settings: Any = None) -> str:
    explicit = _cfg(settings, "TG_STATS_WEBAPP_URL", "")
    if explicit:
        return explicit.rstrip("/") + "/"
    base = (
        _cfg(settings, "TRACKING_PUBLIC_BASE", "")
        or os.getenv("TRACKING_PUBLIC_BASE", "")
        or "https://a.47z.ru/_ava_outreach"
    ).rstrip("/")
    return f"{base}/ui/tg-stats/"


def validate_webapp_init_data(init_data: str, bot_token: str, *, max_age_sec: int = 86400) -> dict[str, Any]:
    """Validate Telegram WebApp initData (HMAC-SHA256). Returns parsed fields or error."""
    raw = (init_data or "").strip()
    if not raw or not bot_token:
        return {"ok": False, "error": "missing_init_data"}
    pairs = dict(parse_qsl(raw, keep_blank_values=True))
    recv_hash = pairs.pop("hash", "")
    if not recv_hash:
        return {"ok": False, "error": "missing_hash"}
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    calc = hmac.new(secret, data_check.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, recv_hash):
        return {"ok": False, "error": "bad_hash"}
    try:
        auth_date = int(pairs.get("auth_date") or "0")
    except ValueError:
        auth_date = 0
    now = int(time.time())
    if auth_date and abs(now - auth_date) > max_age_sec:
        return {"ok": False, "error": "expired"}
    user = {}
    if pairs.get("user"):
        try:
            user = json.loads(pairs["user"])
        except Exception:  # noqa: BLE001
            user = {}
    return {
        "ok": True,
        "user_id": str(user.get("id") or ""),
        "username": user.get("username") or "",
        "auth_date": auth_date,
        "raw": pairs,
    }


def build_outreach_stats(
    *,
    settings: Any,
    outbox: Any,
    runner_status: Callable[[], dict[str, Any]] | None = None,
    queue_snapshot: Callable[[], dict[str, Any]] | None = None,
    telephony_store: Any = None,
) -> dict[str, Any]:
    """Compact operator stats for Telegram text / Mini App."""
    run = {"state": _cfg(settings, "OUTREACH_RUN_STATE", "stopped") or "stopped"}
    if runner_status:
        try:
            run = runner_status() or run
        except Exception as exc:  # noqa: BLE001
            run = {**run, "error": str(exc)[:120]}

    sent_today = 0
    pending = 0
    sent_total = 0
    try:
        sent_today = int(outbox.sent_today_count() or 0)
    except Exception:  # noqa: BLE001
        pass
    try:
        # Prefer store helpers when present
        if hasattr(outbox, "counts"):
            c = outbox.counts() or {}
            pending = int(c.get("pending") or 0)
            sent_total = int(c.get("sent") or 0)
        else:
            with outbox.connect() as conn:
                pending = int(
                    conn.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0]
                )
                sent_total = int(
                    conn.execute(
                        "SELECT COUNT(*) FROM outbox WHERE status IN ('sent','replied')"
                    ).fetchone()[0]
                )
    except Exception:  # noqa: BLE001
        pass

    daily = int(_cfg(settings, "OUTREACH_DAILY_LIMIT", "15") or 15)
    dmin = int(_cfg(settings, "OUTREACH_DELAY_MIN_SECONDS", "600") or 600)
    dmax = int(_cfg(settings, "OUTREACH_DELAY_MAX_SECONDS", "900") or 900)

    queue: dict[str, Any] = {}
    if queue_snapshot:
        try:
            queue = queue_snapshot() or {}
        except Exception as exc:  # noqa: BLE001
            queue = {"error": str(exc)[:120]}

    qc = (queue.get("counts") or {}) if isinstance(queue, dict) else {}
    state = (run.get("state") or "stopped").lower()
    state_ru = {"playing": "Идёт", "paused": "Пауза", "stopped": "Стоп"}.get(state, state)

    engagement = build_engagement(telephony_store=telephony_store)
    eng = engagement.get("summary") or {}

    return {
        "ok": True,
        "at": datetime.now(timezone.utc).isoformat(),
        "run_state": state,
        "run_state_ru": state_ru,
        "sent_today": sent_today,
        "daily_limit": daily,
        "remaining_today": max(0, daily - sent_today),
        "pending": pending,
        "sent_total": sent_total,
        "delay_min_sec": dmin,
        "delay_max_sec": dmax,
        "delay_min_min": round(dmin / 60, 1),
        "delay_max_min": round(dmax / 60, 1),
        "followups_due": int(qc.get("followups_due") or 0),
        "first_touch_in_window": qc.get("first_touch_in_window"),
        "sequences_active": (qc.get("sequences") or {}).get("active")
        if isinstance(qc.get("sequences"), dict)
        else qc.get("sequences_active"),
        "webapp_url": public_webapp_url(settings),
        "days": _calendar_days(outbox, days=21),
        "selected_day": _default_day(outbox),
        "callback_requests": eng.get("callback_requests") or 0,
        "calls_total": eng.get("calls_total") or 0,
        "engagement": engagement,
    }


def _default_day(outbox: Any) -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    try:
        days = outbox.stats_daily(21) or []
        with_sent = [d for d in days if int(d.get("sent") or 0) > 0]
        if with_sent:
            return str(with_sent[-1]["day"])
    except Exception:  # noqa: BLE001
        pass
    return today


def _calendar_days(outbox: Any, *, days: int = 21) -> list[dict[str, Any]]:
    """Last N UTC days with send counts (zeros filled for navigation)."""
    from datetime import date, timedelta

    today = datetime.now(timezone.utc).date()
    by_day: dict[str, dict[str, Any]] = {}
    try:
        for row in outbox.stats_daily(days) or []:
            by_day[str(row["day"])] = {
                "day": str(row["day"]),
                "sent": int(row.get("sent") or 0),
                "replied": int(row.get("replied") or 0),
                "failed": int(row.get("failed") or 0),
            }
    except Exception:  # noqa: BLE001
        pass
    out: list[dict[str, Any]] = []
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        row = by_day.get(d) or {"day": d, "sent": 0, "replied": 0, "failed": 0}
        row["is_today"] = d == today.isoformat()
        out.append(row)
    return out


def _company_lookup(company_ids: list[str]) -> dict[str, dict[str, str]]:
    ids = [str(x).strip() for x in company_ids if str(x or "").strip()]
    if not ids:
        return {}
    db = Path(os.getenv("DATA_DIR", "/opt/ava-outreach/data")) / "clients.db"
    # also try relative to module data
    for cand in (
        db,
        Path(__file__).resolve().parent / "data" / "clients.db",
    ):
        if not cand.is_file():
            continue
        try:
            import sqlite3

            con = sqlite3.connect(str(cand))
            con.row_factory = sqlite3.Row
            qmarks = ",".join("?" for _ in ids)
            rows = con.execute(
                f"SELECT bitrix_id, title, city, inn, phones_json FROM companies WHERE bitrix_id IN ({qmarks})",
                ids,
            ).fetchall()
            con.close()
            out: dict[str, dict[str, str]] = {}
            for r in rows:
                phones = ""
                try:
                    arr = json.loads(r["phones_json"] or "[]")
                    if isinstance(arr, list) and arr:
                        phones = str(arr[0] if not isinstance(arr[0], dict) else arr[0].get("VALUE") or "")
                except Exception:  # noqa: BLE001
                    phones = ""
                out[str(r["bitrix_id"])] = {
                    "company": r["title"] or "",
                    "city": r["city"] or "",
                    "inn": r["inn"] or "",
                    "phone": phones,
                }
            return out
        except Exception:  # noqa: BLE001
            continue
    return {}


def build_day_letters(
    *,
    outbox: Any,
    day: str,
    limit: int = 200,
) -> dict[str, Any]:
    """List sent letters/recipients for one UTC day."""
    d = (day or "").strip()[:10] or _default_day(outbox)
    rows = []
    try:
        rows = outbox.list_sent_on_day(d, limit=limit) or []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200], "day": d, "items": []}

    company_ids = [getattr(r, "company_id", "") or "" for r in rows]
    companies = _company_lookup(company_ids)
    items: list[dict[str, Any]] = []
    for r in rows:
        cid = str(getattr(r, "company_id", "") or "")
        co = companies.get(cid) or {}
        sent_at = getattr(r, "sent_at", None) or ""
        local_time = ""
        if sent_at:
            try:
                # show HH:MM UTC and approx MSK (+3)
                hhmm = sent_at[11:16] if len(sent_at) >= 16 else ""
                local_time = hhmm
                if hhmm and ":" in hhmm:
                    h, m = hhmm.split(":")
                    msk_h = (int(h) + 3) % 24
                    local_time = f"{msk_h:02d}:{m} МСК"
            except Exception:  # noqa: BLE001
                local_time = sent_at
        items.append(
            {
                "id": getattr(r, "id", None),
                "email": getattr(r, "email", "") or "",
                "contact_name": getattr(r, "contact_name", "") or "",
                "company_id": cid,
                "company": co.get("company") or "",
                "city": co.get("city") or "",
                "inn": co.get("inn") or "",
                "phone": co.get("phone") or "",
                "status": getattr(r, "status", "") or "",
                "sent_at": sent_at,
                "sent_at_local": local_time,
                "message_id": getattr(r, "message_id", "") or "",
            }
        )
    return {
        "ok": True,
        "day": d,
        "count": len(items),
        "items": items,
        "days": _calendar_days(outbox, days=21),
    }


def callback_stats(*, limit: int = 30) -> dict[str, Any]:
    """Counts + recent «Заказать звонок» form submits."""
    try:
        from callback_cta import recent_requests

        items = recent_requests(limit=limit) or []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:160], "total": 0, "items": []}
    dial_ok = sum(1 for x in items if x.get("dial_ok"))
    return {
        "ok": True,
        "total": len(items),  # recent window; also expose all-time below
        "recent": items,
        "dial_ok_recent": dial_ok,
        "all_time": _callback_all_time_count(),
    }


def _callback_all_time_count() -> int:
    try:
        from callback_cta import requests_count

        return int(requests_count())
    except Exception:  # noqa: BLE001
        return 0


def telephony_stats(*, store: Any = None, limit: int = 30) -> dict[str, Any]:
    if store is None:
        return {"ok": False, "error": "no_store", "total": 0, "items": []}
    try:
        counts = store.counts() if hasattr(store, "counts") else {}
        items = store.list_recent(limit=limit) if hasattr(store, "list_recent") else []
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:160], "total": 0, "items": []}
    return {
        "ok": True,
        "total": int(counts.get("leads") or 0),
        "ok_count": int(counts.get("ok") or 0),
        "items": items,
    }


def build_engagement(*, telephony_store: Any = None) -> dict[str, Any]:
    """CTA callback requests + AVA telephony leads for Mini App."""
    cb = callback_stats(limit=40)
    tel = telephony_stats(store=telephony_store, limit=40)
    return {
        "ok": True,
        "callbacks": cb,
        "calls": tel,
        "summary": {
            "callback_requests": cb.get("all_time") or 0,
            "callback_recent": len(cb.get("recent") or []),
            "calls_total": tel.get("total") or 0,
            "calls_ok": tel.get("ok_count") or 0,
        },
    }


def require_tg_webapp_user(request: Any, settings: Any) -> str:
    """Validate initData header; return allowlisted Telegram user id or raise ValueError."""
    init_data = ""
    try:
        init_data = (request.headers.get("X-Telegram-Init-Data") or "").strip()
    except Exception:  # noqa: BLE001
        init_data = ""
    token = resolve_bot_token(settings)
    if not token:
        raise ValueError("telegram_bot_not_configured")
    if not init_data:
        raise ValueError("open_via_bot_webapp")
    checked = validate_webapp_init_data(init_data, token)
    if not checked.get("ok"):
        raise ValueError(str(checked.get("error") or "bad_init_data"))
    user_id = str(checked.get("user_id") or "")
    if not chat_allowed(user_id, settings):
        raise ValueError("chat_not_allowlisted")
    return user_id


def format_stats_text(stats: dict[str, Any]) -> str:
    lines = [
        "Quantum Panel · Outreach",
        "",
        f"Статус: {stats.get('run_state_ru') or stats.get('run_state')}",
        f"Сегодня: {stats.get('sent_today', 0)} / {stats.get('daily_limit', '—')} "
        f"(осталось {stats.get('remaining_today', '—')})",
        f"Всего отправлено: {stats.get('sent_total', 0)}",
        f"В очереди (pending): {stats.get('pending', 0)}",
        f"Due follow-up: {stats.get('followups_due', 0)}",
        f"Пауза между письмами: {stats.get('delay_min_min')}–{stats.get('delay_max_min')} мин",
        f"Кнопка «Перезвонить»: {stats.get('callback_requests', 0)} заявок",
        f"Звонки AVA: {stats.get('calls_total', 0)}",
    ]
    if stats.get("first_touch_in_window") is not None:
        lines.append(f"Первые в окне сейчас: {stats.get('first_touch_in_window')}")
    if stats.get("sequences_active") is not None:
        lines.append(f"Активных цепочек: {stats.get('sequences_active')}")
    return "\n".join(lines)


def reply_keyboard() -> str:
    """JSON reply_markup for sendMessage."""
    return json.dumps(
        {
            "keyboard": [
                [{"text": BTN_STATS}, {"text": BTN_QUEUE}],
                [{"text": BTN_HELP}],
            ],
            "resize_keyboard": True,
            "is_persistent": True,
        },
        ensure_ascii=False,
    )


def webapp_inline_keyboard(url: str) -> str:
    return json.dumps(
        {
            "inline_keyboard": [
                [{"text": "Открыть статистику", "web_app": {"url": url}}],
            ]
        },
        ensure_ascii=False,
    )


def setup_bot_commands_and_menu(token: str, webapp_url: str) -> dict[str, Any]:
    cmds = telegram_api(
        token,
        "setMyCommands",
        {
            "commands": json.dumps(
                [
                    {"command": "start", "description": "Меню Quantum Panel"},
                    {"command": "stats", "description": "Статистика Outreach"},
                    {"command": "queue", "description": "Очередь кратко"},
                    {"command": "app", "description": "Открыть Mini App"},
                ],
                ensure_ascii=False,
            )
        },
    )
    menu = telegram_api(
        token,
        "setChatMenuButton",
        {
            "menu_button": json.dumps(
                {"type": "web_app", "text": "Статистика", "web_app": {"url": webapp_url}},
                ensure_ascii=False,
            )
        },
    )
    return {"commands": cmds, "menu": menu}


class TelegramPanelBot(threading.Thread):
    """Long-poll getUpdates for /stats and keyboard buttons."""

    def __init__(
        self,
        *,
        settings: Any,
        stats_fn: Callable[[], dict[str, Any]],
    ) -> None:
        super().__init__(daemon=True, name="tg-panel-bot")
        self._settings = settings
        self._stats_fn = stats_fn
        self._shutdown = threading.Event()
        self._offset = 0
        self.last_ok_at: str | None = None
        self.last_error: str | None = None

    def shutdown(self) -> None:
        self._shutdown.set()

    def _send(self, token: str, chat_id: str, text: str, *, reply_markup: str | None = None) -> None:
        params: dict[str, Any] = {"chat_id": chat_id, "text": text[:3900]}
        if reply_markup:
            params["reply_markup"] = reply_markup
        out = telegram_api(token, "sendMessage", params)
        if not out.get("ok"):
            logger.warning("tg panel send failed: %s", out.get("error"))

    def _handle(self, token: str, msg: dict[str, Any]) -> None:
        chat = msg.get("chat") or {}
        chat_id = str(chat.get("id") or "")
        text = (msg.get("text") or "").strip()
        if not chat_id or not text:
            return
        if not chat_allowed(chat_id, self._settings):
            self._send(
                token,
                chat_id,
                "Нет доступа. Подключите chat id в Настройках Quantum Panel.",
            )
            return

        low = text.lower()
        webapp = public_webapp_url(self._settings)

        if low in ("/start", "start", BTN_HELP.lower(), "/help", "помощь", BTN_HELP):
            self._send(
                token,
                chat_id,
                "Quantum Panel · Outreach\n\n"
                "Кнопки ниже или команды:\n"
                "/stats — статистика\n"
                "/queue — очередь\n"
                "/app — Mini App\n\n"
                "Меню слева от поля ввода → «Статистика».",
                reply_markup=reply_keyboard(),
            )
            self._send(
                token,
                chat_id,
                "Открыть приложение:",
                reply_markup=webapp_inline_keyboard(webapp),
            )
            return

        if low in ("/app", "app", "мини", "mini app"):
            self._send(
                token,
                chat_id,
                "Статистика Outreach:",
                reply_markup=webapp_inline_keyboard(webapp),
            )
            return

        want_stats = low in ("/stats", "stats", "статистика", BTN_STATS.lower()) or text == BTN_STATS
        want_queue = low in ("/queue", "queue", "очередь", BTN_QUEUE.lower()) or text == BTN_QUEUE
        if want_stats or want_queue:
            try:
                stats = self._stats_fn()
            except Exception as exc:  # noqa: BLE001
                self._send(token, chat_id, f"Ошибка статистики: {exc}")
                return
            body = format_stats_text(stats)
            if want_queue:
                body += (
                    f"\n\nОчередь: pending {stats.get('pending', 0)}, "
                    f"due {stats.get('followups_due', 0)}"
                )
            self._send(token, chat_id, body, reply_markup=reply_keyboard())
            self._send(
                token,
                chat_id,
                "Подробнее в приложении:",
                reply_markup=webapp_inline_keyboard(webapp),
            )

    def run(self) -> None:
        logger.info("telegram panel bot started")
        # Drop backlog once so discover/UI getUpdates aren't confused forever
        bootstrapped = False
        while not self._shutdown.is_set():
            if not _cfg_bool(self._settings, "TG_PANEL_BOT_ENABLED", True):
                self._shutdown.wait(5)
                continue
            token = resolve_bot_token(self._settings)
            if not token:
                self.last_error = "no_token"
                self._shutdown.wait(15)
                continue
            if not bootstrapped:
                try:
                    setup_bot_commands_and_menu(token, public_webapp_url(self._settings))
                    # skip old updates
                    out = telegram_api(
                        token,
                        "getUpdates",
                        {"timeout": "0", "offset": "-1"},
                    )
                    if out.get("ok"):
                        for upd in out.get("result") or []:
                            self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
                    bootstrapped = True
                    self.last_error = None
                except Exception as exc:  # noqa: BLE001
                    self.last_error = str(exc)[:200]
                    logger.warning("tg panel bootstrap failed: %s", exc)
                    self._shutdown.wait(10)
                    continue

            out = telegram_api(
                token,
                "getUpdates",
                {
                    "timeout": "25",
                    "offset": str(self._offset),
                    "allowed_updates": json.dumps(["message"]),
                },
            )
            if not out.get("ok"):
                self.last_error = str(out.get("error") or "getUpdates_failed")[:200]
                # Conflict with another getUpdates — back off
                self._shutdown.wait(5 if "Conflict" not in self.last_error else 20)
                continue
            self.last_ok_at = datetime.now(timezone.utc).isoformat()
            self.last_error = None
            for upd in out.get("result") or []:
                self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
                msg = upd.get("message") or {}
                try:
                    self._handle(token, msg)
                except Exception:  # noqa: BLE001
                    logger.exception("tg panel handle failed")
        logger.info("telegram panel bot stopped")
