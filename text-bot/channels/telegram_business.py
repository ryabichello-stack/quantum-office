"""Telegram Business: reply as the human account (not as a bot).

Official Bot API path (no Telethon userbot / no account ban risk):
1) @BotFather → Bot Settings → Business Mode → Enable
2) On the phone account: Settings → Telegram Business → Chatbots → @YourBot
3) Grant read + reply; choose which chats (e.g. new chats only)

Incoming customer DMs arrive as ``business_message`` updates.
Outgoing replies use ``business_connection_id`` so the peer sees *your* name/avatar.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("ava-text-bot.telegram-business")

_LOCK = threading.Lock()
_CONNECTIONS: dict[str, dict[str, Any]] = {}
_PAUSE_UNTIL: dict[str, float] = {}  # chat_id -> unix ts


def enabled() -> bool:
    raw = (os.getenv("TELEGRAM_BUSINESS_ENABLED", "true") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def auto_reply_enabled() -> bool:
    raw = (os.getenv("TELEGRAM_BUSINESS_AUTO_REPLY", "true") or "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def owner_pause_seconds() -> int:
    try:
        return max(0, int(os.getenv("TELEGRAM_BUSINESS_OWNER_PAUSE_SECONDS", "1800")))
    except ValueError:
        return 1800


def _store_path() -> Path:
    data = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
    data.mkdir(parents=True, exist_ok=True)
    return data / "telegram_business.json"


def load_connections() -> None:
    path = _store_path()
    if not path.is_file():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        conns = raw.get("connections") or {}
        with _LOCK:
            _CONNECTIONS.clear()
            for k, v in conns.items():
                if isinstance(v, dict) and v.get("id"):
                    _CONNECTIONS[str(k)] = v
        logger.info("telegram business connections loaded n=%s", len(_CONNECTIONS))
    except Exception:
        logger.exception("failed to load telegram business connections")


def _persist() -> None:
    path = _store_path()
    with _LOCK:
        payload = {"connections": dict(_CONNECTIONS)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_connection(conn: dict[str, Any]) -> None:
    cid = str(conn.get("id") or "").strip()
    if not cid:
        return
    user = conn.get("user") or {}
    record = {
        "id": cid,
        "user_id": str(user.get("id") or ""),
        "user_chat_id": str(conn.get("user_chat_id") or ""),
        "is_enabled": bool(conn.get("is_enabled", True)),
        "can_reply": bool(conn.get("can_reply", True)),
        "rights": conn.get("rights") or {},
        "updated_at": int(time.time()),
    }
    with _LOCK:
        if record["is_enabled"]:
            _CONNECTIONS[cid] = record
        else:
            _CONNECTIONS.pop(cid, None)
    _persist()
    logger.info(
        "business connection %s enabled=%s user=%s",
        cid[:12],
        record["is_enabled"],
        record["user_id"],
    )


def get_connection(connection_id: str) -> Optional[dict[str, Any]]:
    with _LOCK:
        return dict(_CONNECTIONS.get(str(connection_id) or "") or {}) or None


def list_connections() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_CONNECTIONS.values())


def status() -> dict[str, Any]:
    return {
        "enabled": enabled(),
        "auto_reply": auto_reply_enabled(),
        "connections": len(list_connections()),
        "owner_pause_seconds": owner_pause_seconds(),
    }


def pause_chat(chat_id: str | int, *, seconds: int | None = None) -> None:
    sec = owner_pause_seconds() if seconds is None else max(0, int(seconds))
    if sec <= 0:
        return
    key = str(chat_id)
    with _LOCK:
        _PAUSE_UNTIL[key] = time.time() + sec
    logger.info("business auto-reply paused chat_id=%s for %ss", key, sec)


def is_paused(chat_id: str | int) -> bool:
    key = str(chat_id)
    with _LOCK:
        until = _PAUSE_UNTIL.get(key) or 0.0
    return time.time() < until


def parse_business_message(update: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Normalize business_message / edited_business_message into a dict or None."""
    message = update.get("business_message") or update.get("edited_business_message")
    if not isinstance(message, dict):
        return None
    conn_id = str(message.get("business_connection_id") or "").strip()
    if not conn_id:
        return None
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    text = str(message.get("text") or "").strip()
    chat_id = chat.get("id")
    if chat_id is None:
        return None
    return {
        "connection_id": conn_id,
        "chat_id": chat_id,
        "user_id": str(from_user.get("id") or chat_id),
        "from_is_bot": bool(from_user.get("is_bot")),
        "text": text,
        "chat_type": str(chat.get("type") or "private"),
        "message": message,
    }
