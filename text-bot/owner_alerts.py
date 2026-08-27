"""Owner alerts → Telegram personal bot + Max DM.

Used for high-signal events: outreach replies, new messenger chats,
inbound call leads, website callback forms.

Env:
  OWNER_ALERT_ENABLED=true
  OWNER_ALERT_TELEGRAM_CHAT_ID=   — default: first SECRETARY_OWNER_IDS
  OWNER_ALERT_MAX_USER_ID=        — Max user id for your dialog with the bot
  OWNER_ALERT_CHANNELS=telegram,max
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

logger = logging.getLogger("ava-text-bot.owner_alerts")

_lock = threading.Lock()

KIND_LABELS = {
    "outreach_reply": "Ответ на рассылку",
    "new_chat": "Новый чат",
    "inbound_call": "Входящий звонок",
    "form_callback": "Заявка с формы",
}


def enabled() -> bool:
    return (os.getenv("OWNER_ALERT_ENABLED", "true") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))


def _alerts_db() -> Path:
    return _data_dir() / "owner_alerts.db"


def _telegram_chat_ids() -> list[str]:
    raw = (
        os.getenv("OWNER_ALERT_TELEGRAM_CHAT_ID")
        or os.getenv("SECRETARY_OWNER_IDS")
        or ""
    ).strip()
    return [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]


def _max_user_id() -> str:
    return (os.getenv("OWNER_ALERT_MAX_USER_ID") or "").strip()


def _channels() -> set[str]:
    raw = (os.getenv("OWNER_ALERT_CHANNELS") or "telegram,max").strip().lower()
    return {p.strip() for p in raw.split(",") if p.strip()}


def _init_db() -> None:
    path = _alerts_db()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(str(path))
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert_dedupe (
                    dedupe_key TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def claim_once(dedupe_key: str, *, kind: str) -> bool:
    """Return True if this key was not seen before (claim succeeds)."""
    if not dedupe_key:
        return True
    _init_db()
    with _lock:
        conn = sqlite3.connect(str(_alerts_db()))
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO alert_dedupe (dedupe_key, kind) VALUES (?, ?)",
                (str(dedupe_key)[:400], kind[:80]),
            )
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def format_alert(*, kind: str, title: str = "", body: str = "", meta: Optional[dict] = None) -> str:
    label = KIND_LABELS.get(kind, kind or "Событие")
    head = f"[{label}]"
    if title:
        head = f"{head} {title.strip()}"
    parts = [head]
    if body:
        parts.append("")
        parts.append(body.strip()[:3500])
    if meta:
        extras = []
        for k in ("channel", "from", "phone", "email", "company", "classification", "source"):
            v = meta.get(k)
            if v:
                extras.append(f"{k}: {v}")
        if extras and not body:
            parts.append("")
            parts.extend(extras)
    return "\n".join(parts).strip()[:4000]


def _send_telegram(text: str) -> dict[str, Any]:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    chat_ids = _telegram_chat_ids()
    if not token or not chat_ids:
        return {"ok": False, "skipped": "telegram_not_configured"}
    results = []
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps(
            {"chat_id": chat_id, "text": text[:4096]},
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                results.append(
                    {
                        "chat_id": chat_id,
                        "ok": True,
                        "status": resp.status,
                    }
                )
        except urllib.error.HTTPError as exc:
            err = exc.read().decode("utf-8", errors="replace")[:300]
            logger.error("owner alert telegram HTTP %s chat_id=%s: %s", exc.code, chat_id, err)
            results.append({"chat_id": chat_id, "ok": False, "error": err})
        except Exception as exc:  # noqa: BLE800
            logger.exception("owner alert telegram failed chat_id=%s", chat_id)
            results.append({"chat_id": chat_id, "ok": False, "error": str(exc)[:200]})
    ok_any = any(r.get("ok") for r in results)
    return {"ok": ok_any, "results": results}


def _send_max(text: str) -> dict[str, Any]:
    token = (os.getenv("MAX_BOT_TOKEN") or "").strip()
    user_id = _max_user_id()
    if not token or not user_id:
        return {"ok": False, "skipped": "max_not_configured"}
    if (os.getenv("MAX_ENABLED") or "").strip().lower() not in {"1", "true", "yes", "on"}:
        return {"ok": False, "skipped": "max_disabled"}
    api_base = (os.getenv("MAX_API_BASE") or "https://platform-api2.max.ru").rstrip("/")
    url = f"{api_base}/messages?{urlencode({'user_id': user_id})}"
    payload = json.dumps({"text": text[:4000]}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": token,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return {"ok": True, "user_id": user_id, "status": resp.status}
    except urllib.error.HTTPError as exc:
        err = exc.read().decode("utf-8", errors="replace")[:300]
        logger.error("owner alert max HTTP %s user_id=%s: %s", exc.code, user_id, err)
        return {"ok": False, "user_id": user_id, "error": err}
    except Exception as exc:  # noqa: BLE800
        logger.exception("owner alert max failed user_id=%s", user_id)
        return {"ok": False, "user_id": user_id, "error": str(exc)[:200]}


def notify_owner(
    *,
    kind: str,
    title: str = "",
    body: str = "",
    meta: Optional[dict[str, Any]] = None,
    dedupe_key: Optional[str] = None,
) -> dict[str, Any]:
    """Fan-out one alert to configured owner Telegram + Max dialogs."""
    kind = (kind or "event").strip()
    if not enabled():
        return {"ok": False, "skipped": "disabled"}
    if dedupe_key and not claim_once(dedupe_key, kind=kind):
        return {"ok": True, "deduped": True, "dedupe_key": dedupe_key}

    text = format_alert(kind=kind, title=title, body=body, meta=meta)
    channels = _channels()
    out: dict[str, Any] = {"ok": False, "kind": kind, "text_chars": len(text)}
    if "telegram" in channels:
        out["telegram"] = _send_telegram(text)
    if "max" in channels:
        out["max"] = _send_max(text)

    out["ok"] = bool(
        (out.get("telegram") or {}).get("ok")
        or (out.get("max") or {}).get("ok")
    )
    logger.info(
        "owner alert kind=%s ok=%s tg=%s max=%s",
        kind,
        out["ok"],
        (out.get("telegram") or {}).get("ok"),
        (out.get("max") or {}).get("ok"),
    )
    return out


def should_alert_new_chat(*, channel: str, user_id: str, role: str) -> bool:
    """Guest chats on messenger channels only; skip owner/trainee/smoke."""
    if not enabled():
        return False
    if role in {"owner", "trainee"}:
        return False
    ch = (channel or "").strip().lower()
    if ch not in {"telegram", "telegram_business", "max", "whatsapp", "vk"}:
        return False
    uid = str(user_id or "").strip().lower()
    if not uid or uid in {"1", "0"}:
        return False
    if "smoke" in uid or uid.startswith("test"):
        return False
    # Don't alert the owner about their own Business/test chats.
    owners = {x.lower() for x in _telegram_chat_ids()}
    if uid in owners:
        return False
    max_owner = _max_user_id().lower()
    if max_owner and uid == max_owner and ch == "max":
        return False
    return True


def maybe_alert_new_chat(
    *,
    channel: str,
    user_id: str,
    role: str,
    text: str,
    history_empty: bool,
) -> Optional[dict[str, Any]]:
    if not history_empty:
        return None
    if not should_alert_new_chat(channel=channel, user_id=user_id, role=role):
        return None
    preview = (text or "").strip()
    if preview.startswith("/"):
        preview = preview if preview.lower() in {"/start", "start"} else preview[:200]
    channel_label = {
        "telegram": "Telegram-бот",
        "telegram_business": "Telegram (личный / Business)",
        "max": "Max",
        "whatsapp": "WhatsApp",
        "vk": "VK",
    }.get(channel, channel)
    body_lines = [
        f"Канал: {channel_label}",
        f"User id: {user_id}",
    ]
    if preview:
        body_lines.append(f"Сообщение: {preview[:500]}")
    return notify_owner(
        kind="new_chat",
        title=channel_label,
        body="\n".join(body_lines),
        meta={"channel": channel, "from": str(user_id)},
        dedupe_key=f"new_chat:{channel}:{user_id}",
    )


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "telegram_targets": len(_telegram_chat_ids()),
        "max_configured": bool(_max_user_id()),
        "channels": sorted(_channels()),
    }
