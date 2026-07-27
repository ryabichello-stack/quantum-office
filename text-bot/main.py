"""
ava-text-bot — Quantum Labs ИИ-секретарь.

Ядро диалога channel-agnostic (secretary.py).
Каналы-доставки:
  - Telegram (@Quantum_office_bot)
  - HTTP API: POST /api/chat  (web/Bitrix/любая среда)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from secretary import secretary

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-text-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
WEBHOOK_TOKEN = os.getenv("OFFICE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()
POLL_INTERVAL_S = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1"))

app = FastAPI(title="Quantum Labs Secretary", version="0.2.0")
_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _check_api_token(x_webhook_token: Optional[str] = None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


# --------------------
# Universal chat API (any environment)
# --------------------


class ChatRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)
    user_id: str = Field(..., min_length=1, max_length=200, description="Stable user id in this channel")
    channel: str = Field(
        default="api",
        description="telegram|api|web|bitrix|owner|...",
    )
    reply_to: Optional[str] = Field(
        default=None,
        description="For telegram file delivery: chat_id",
    )
    scenario: Optional[str] = Field(
        default=None,
        description="Optional scenario override for this turn: secretary|calendar|conference|knowledge|files|briefing|client_prep|office",
    )


class ChatResetRequest(BaseModel):
    user_id: str
    channel: str = "api"


@app.post("/api/chat")
def api_chat(req: ChatRequest, x_webhook_token: Optional[str] = Header(None)):
    """Secretary dialogue entrypoint for any channel/environment."""
    _check_api_token(x_webhook_token)
    result = secretary.handle(
        channel=req.channel,
        user_id=req.user_id,
        text=req.text,
        reply_to=req.reply_to,
        scenario=req.scenario,
    )
    return result


@app.post("/api/chat/reset")
def api_chat_reset(req: ChatResetRequest, x_webhook_token: Optional[str] = Header(None)):
    _check_api_token(x_webhook_token)
    reply = secretary.reset(req.channel, req.user_id)
    return {"ok": True, "reply": reply, "channel": req.channel, "user_id": req.user_id}


# --------------------
# Telegram transport
# --------------------


def _tg_post(method: str, payload: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_telegram(chat_id: str | int, text: str) -> None:
    _tg_post(
        "sendMessage",
        {"chat_id": chat_id, "text": str(text)[:4096]},
        timeout=20.0,
    )


def _safe_send(chat_id: str | int, text: str) -> None:
    try:
        send_telegram(chat_id, text)
    except Exception:
        logger.exception("send_telegram failed chat_id=%s", chat_id)


def handle_telegram_update(update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    text = str(message.get("text") or "").strip()
    if not text:
        return

    logger.info("telegram incoming chat_id=%s text=%r", chat_id, text[:120])
    result = secretary.handle(
        channel="telegram",
        user_id=str(chat_id),
        text=text,
        reply_to=str(chat_id),
    )
    _safe_send(chat_id, result.get("reply") or "…")
    logger.info(
        "telegram replied chat_id=%s ok=%s chars=%s",
        chat_id,
        result.get("ok"),
        len(result.get("reply") or ""),
    )


def poll_loop() -> None:
    offset: int | None = None
    logger.info("Telegram poll loop started")
    try:
        _tg_post("deleteWebhook", {"drop_pending_updates": False}, timeout=15.0)
        logger.info("webhook cleared for polling")
    except Exception:
        logger.exception("deleteWebhook failed")

    while not _stop_event.is_set():
        if not TELEGRAM_BOT_TOKEN:
            time.sleep(5)
            continue
        try:
            payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message"]}
            if offset is not None:
                payload["offset"] = offset
            out = _tg_post("getUpdates", payload, timeout=35.0)
            if not out.get("ok"):
                logger.warning("getUpdates not ok: %s", out)
                time.sleep(3)
                continue
            for upd in out.get("result") or []:
                offset = int(upd.get("update_id", 0)) + 1
                try:
                    handle_telegram_update(upd)
                except Exception:
                    logger.exception("update failed: %s", upd.get("update_id"))
        except urllib.error.URLError as exc:
            logger.warning("poll error: %s", exc)
            time.sleep(3)
        except Exception:
            logger.exception("poll unexpected")
            time.sleep(3)
        time.sleep(POLL_INTERVAL_S)


@app.on_event("startup")
def on_startup() -> None:
    global _poll_thread
    secretary.startup(OPENAI_API_KEY)
    if TELEGRAM_BOT_TOKEN:
        _poll_thread = threading.Thread(target=poll_loop, name="telegram-poll", daemon=True)
        _poll_thread.start()
        logger.info("telegram channel enabled model=%s", OPENAI_MODEL)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN missing — API channel still available")


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_event.set()


@app.get("/health")
def health() -> dict[str, Any]:
    from ava_client import KNOWLEDGE_BASE, OPENAI_TOOLS
    from scenarios import get_bundle, list_scenarios

    b = get_bundle()
    return {
        "status": "ok" if secretary.ready() else "degraded",
        "service": "ava-text-bot",
        "role": "quantum-labs-secretary",
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "mailer_base": AVA_MAILER_BASE,
        "knowledge_base": KNOWLEDGE_BASE,
        "owners_configured": len(b.owners),
        "scenarios": [s.id for s in list_scenarios("owner")],
        "channels": ["telegram", "api", "web", "bitrix"],
        "endpoints": ["/api/chat", "/api/chat/reset", "/health"],
        "tools": [t["function"]["name"] for t in OPENAI_TOOLS if t.get("type") == "function"],
    }
