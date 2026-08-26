"""
ava-text-bot — Quantum Labs ИИ-секретарь.

Ядро диалога channel-agnostic (secretary.py).
Каналы-доставки:
  - Telegram (@Quantum_office_bot) — long poll
  - WhatsApp / Max / VK — webhooks (guest, Second Brain faq-safe)
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
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field

from channels import channel_status, max_messenger, telegram_business, vk, whatsapp
from scenarios import looks_like_outbound_request
from secretary import secretary

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-text-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BUSINESS_BOT_TOKEN = os.getenv("TELEGRAM_BUSINESS_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
WEBHOOK_TOKEN = os.getenv("OFFICE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()
POLL_INTERVAL_S = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1"))
TG_HANDLE_WORKERS = max(1, int(os.getenv("TELEGRAM_HANDLE_WORKERS", "4")))

app = FastAPI(title="Quantum Labs Secretary", version="0.3.0")
_poll_thread: threading.Thread | None = None
_business_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()
_update_pool = ThreadPoolExecutor(
    max_workers=TG_HANDLE_WORKERS, thread_name_prefix="tg-handle"
)


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
        description="telegram|whatsapp|max|vk|api|web|bitrix|owner|...",
    )
    reply_to: Optional[str] = Field(
        default=None,
        description="For telegram file delivery: chat_id",
    )
    scenario: Optional[str] = Field(
        default=None,
        description="Optional scenario override for this turn",
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
# Messenger webhooks (WhatsApp / Max / VK)
# --------------------


@app.api_route("/webhooks/whatsapp", methods=["GET", "POST"])
async def whatsapp_webhook(request: Request):
    if request.method == "GET":
        qp = request.query_params
        challenge = whatsapp.verify_webhook(
            mode=qp.get("hub.mode", ""),
            token=qp.get("hub.verify_token", ""),
            challenge=qp.get("hub.challenge", ""),
        )
        if challenge is None:
            raise HTTPException(status_code=403, detail="verify_failed")
        return Response(content=challenge, media_type="text/plain")

    raw = await request.body()
    sig = request.headers.get("X-Hub-Signature-256")
    if not whatsapp.signature_ok(raw, sig):
        raise HTTPException(status_code=403, detail="bad_signature")
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad_json") from exc
    return whatsapp.handle_webhook(payload, secretary_handle=secretary.handle)


@app.post("/webhooks/max")
async def max_webhook(
    request: Request,
    x_max_bot_api_secret: Optional[str] = Header(None, alias="X-Max-Bot-Api-Secret"),
):
    if not max_messenger.secret_ok(x_max_bot_api_secret):
        raise HTTPException(status_code=403, detail="bad_secret")
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad_json") from exc
    return max_messenger.handle_webhook(payload, secretary_handle=secretary.handle)


@app.post("/webhooks/vk")
async def vk_webhook(request: Request):
    try:
        payload = await request.json()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="bad_json") from exc
    body, code = vk.handle_callback(payload, secretary_handle=secretary.handle)
    return Response(content=body, media_type="text/plain", status_code=code)


# --------------------
# Telegram transport
# --------------------


def _tg_post(
    method: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    tok = (token or TELEGRAM_BOT_TOKEN or "").strip()
    if not tok:
        raise RuntimeError("telegram_token_missing")
    url = f"https://api.telegram.org/bot{tok}/{method}"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _business_token() -> str:
    return (TELEGRAM_BUSINESS_BOT_TOKEN or TELEGRAM_BOT_TOKEN or "").strip()


def send_telegram(
    chat_id: str | int,
    text: str,
    *,
    business_connection_id: str | None = None,
    token: str | None = None,
) -> None:
    payload: dict[str, Any] = {"chat_id": chat_id, "text": str(text)[:4096]}
    if business_connection_id:
        payload["business_connection_id"] = business_connection_id
    tok = token
    if business_connection_id:
        tok = tok or _business_token()
    _tg_post("sendMessage", payload, token=tok, timeout=20.0)


def _safe_send(
    chat_id: str | int,
    text: str,
    *,
    business_connection_id: str | None = None,
    token: str | None = None,
) -> None:
    try:
        send_telegram(
            chat_id,
            text,
            business_connection_id=business_connection_id,
            token=token,
        )
    except Exception:
        logger.exception(
            "send_telegram failed chat_id=%s business=%s",
            chat_id,
            bool(business_connection_id),
        )


def _safe_typing(
    chat_id: str | int,
    *,
    business_connection_id: str | None = None,
    token: str | None = None,
) -> None:
    try:
        payload: dict[str, Any] = {"chat_id": chat_id, "action": "typing"}
        if business_connection_id:
            payload["business_connection_id"] = business_connection_id
        tok = token
        if business_connection_id:
            tok = tok or _business_token()
        _tg_post("sendChatAction", payload, token=tok, timeout=10.0)
    except Exception:
        logger.debug("sendChatAction failed chat_id=%s", chat_id, exc_info=True)


def handle_business_message(update: dict[str, Any]) -> None:
    """Customer DM to the human Business account — reply *as the account*."""
    if not telegram_business.enabled():
        return
    parsed = telegram_business.parse_business_message(update)
    if not parsed:
        return
    conn_id = parsed["connection_id"]
    chat_id = parsed["chat_id"]
    text = parsed["text"]
    user_id = parsed["user_id"]
    biz_tok = _business_token()

    conn = telegram_business.get_connection(conn_id)
    owner_id = str((conn or {}).get("user_id") or "")

    # Owner typed from the phone → pause auto-reply so we don't talk over them.
    if owner_id and user_id == owner_id:
        telegram_business.pause_chat(chat_id)
        logger.info("business owner message chat_id=%s — auto-reply paused", chat_id)
        return

    if not text:
        return
    if not telegram_business.auto_reply_enabled():
        logger.info("business auto-reply disabled; skip chat_id=%s", chat_id)
        return
    if telegram_business.is_paused(chat_id):
        logger.info("business chat paused chat_id=%s — skip", chat_id)
        return
    if conn and not conn.get("is_enabled", True):
        return

    logger.info(
        "business incoming chat_id=%s user_id=%s text=%r",
        chat_id,
        user_id,
        text[:120],
    )
    _safe_typing(chat_id, business_connection_id=conn_id, token=biz_tok)
    result = secretary.handle(
        channel="telegram_business",
        user_id=user_id,
        text=text,
        reply_to=str(chat_id),
        chat_type=parsed.get("chat_type") or "private",
    )
    _safe_send(
        chat_id,
        result.get("reply") or "…",
        business_connection_id=conn_id,
        token=biz_tok,
    )
    logger.info(
        "business replied chat_id=%s user_id=%s ok=%s chars=%s",
        chat_id,
        user_id,
        result.get("ok"),
        len(result.get("reply") or ""),
    )


def handle_telegram_update(update: dict[str, Any], *, token: str | None = None) -> None:
    # Business connection lifecycle (connect / disconnect / rights change)
    if "business_connection" in update:
        telegram_business.upsert_connection(update.get("business_connection") or {})
        return

    if "business_message" in update or "edited_business_message" in update:
        handle_business_message(update)
        return

    message = update.get("message") or {}
    chat = message.get("chat") or {}
    from_user = message.get("from") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    text = str(message.get("text") or "").strip()
    if not text:
        return

    chat_type = str(chat.get("type") or "private")
    user_id = str(from_user.get("id") or chat_id)
    tok = token or TELEGRAM_BOT_TOKEN

    logger.info(
        "telegram incoming chat_id=%s user_id=%s chat_type=%s text=%r",
        chat_id,
        user_id,
        chat_type,
        text[:120],
    )

    _safe_typing(chat_id, token=tok)
    if looks_like_outbound_request(text):
        _safe_send(
            chat_id,
            "Принял. Готовлю/веду звонок — напишу, как будет результат (это может занять 1–2 мин).",
            token=tok,
        )

    result = secretary.handle(
        channel="telegram",
        user_id=user_id,
        text=text,
        reply_to=str(chat_id),
        chat_type=chat_type,
    )
    _safe_send(chat_id, result.get("reply") or "…", token=tok)
    logger.info(
        "telegram replied chat_id=%s user_id=%s role=%s ok=%s chars=%s",
        chat_id,
        user_id,
        result.get("role"),
        result.get("ok"),
        len(result.get("reply") or ""),
    )


def _handle_update_safe(update: dict[str, Any], *, token: str | None = None) -> None:
    try:
        handle_telegram_update(update, token=token)
    except Exception:
        logger.exception("update failed: %s", update.get("update_id"))


def poll_loop(*, token: str, name: str, allow_direct_messages: bool = True) -> None:
    offset: int | None = None
    logger.info("Telegram poll loop started name=%s workers=%s", name, TG_HANDLE_WORKERS)
    try:
        _tg_post(
            "deleteWebhook",
            {"drop_pending_updates": False},
            token=token,
            timeout=15.0,
        )
        logger.info("webhook cleared for polling name=%s", name)
    except Exception:
        logger.exception("deleteWebhook failed name=%s", name)

    allowed = [
        "business_connection",
        "business_message",
        "edited_business_message",
    ]
    if allow_direct_messages:
        allowed.insert(0, "message")

    while not _stop_event.is_set():
        if not token:
            time.sleep(5)
            continue
        try:
            payload: dict[str, Any] = {"timeout": 25, "allowed_updates": allowed}
            if offset is not None:
                payload["offset"] = offset
            out = _tg_post("getUpdates", payload, token=token, timeout=35.0)
            if not out.get("ok"):
                logger.warning("getUpdates not ok name=%s: %s", name, out)
                time.sleep(3)
                continue
            for upd in out.get("result") or []:
                offset = int(upd.get("update_id", 0)) + 1
                _update_pool.submit(_handle_update_safe, upd, token=token)
        except urllib.error.URLError as exc:
            logger.warning("poll error name=%s: %s", name, exc)
            time.sleep(3)
        except Exception:
            logger.exception("poll unexpected name=%s", name)
            time.sleep(3)
        time.sleep(POLL_INTERVAL_S)


@app.on_event("startup")
def on_startup() -> None:
    global _poll_thread, _business_poll_thread
    secretary.startup(OPENAI_API_KEY)
    telegram_business.load_connections()
    if TELEGRAM_BOT_TOKEN:
        _poll_thread = threading.Thread(
            target=poll_loop,
            kwargs={
                "token": TELEGRAM_BOT_TOKEN,
                "name": "personal",
                "allow_direct_messages": True,
            },
            name="telegram-poll",
            daemon=True,
        )
        _poll_thread.start()
        logger.info("telegram personal bot enabled model=%s", OPENAI_MODEL)
    else:
        logger.warning("TELEGRAM_BOT_TOKEN missing — personal bot off")

    if TELEGRAM_BUSINESS_BOT_TOKEN:
        # Commercial bot: primarily Business / Secretary Mode updates.
        # Also accept direct /start to the bot itself.
        same = TELEGRAM_BUSINESS_BOT_TOKEN == TELEGRAM_BOT_TOKEN
        if not same:
            _business_poll_thread = threading.Thread(
                target=poll_loop,
                kwargs={
                    "token": TELEGRAM_BUSINESS_BOT_TOKEN,
                    "name": "business",
                    "allow_direct_messages": True,
                },
                name="telegram-business-poll",
                daemon=True,
            )
            _business_poll_thread.start()
            logger.info("telegram business bot poller enabled")
        else:
            logger.info("telegram business token same as personal — single poller")
    else:
        logger.warning("TELEGRAM_BUSINESS_BOT_TOKEN missing — connect commercial bot later")

    ch = channel_status()
    biz = telegram_business.status()
    logger.info(
        "messenger channels whatsapp=%s max=%s vk=%s telegram_business=%s conns=%s biz_token=%s",
        ch["whatsapp"].get("enabled"),
        ch["max"].get("enabled"),
        ch["vk"].get("enabled"),
        biz.get("enabled"),
        biz.get("connections"),
        bool(TELEGRAM_BUSINESS_BOT_TOKEN),
    )


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_event.set()


@app.get("/health")
def health() -> dict[str, Any]:
    from ava_client import KNOWLEDGE_BASE, OPENAI_TOOLS
    from scenarios import get_bundle, list_scenarios

    b = get_bundle()
    messengers = channel_status()
    biz = telegram_business.status()
    enabled_channels = ["telegram", "api", "web", "bitrix"]
    if biz.get("enabled"):
        enabled_channels.append("telegram_business")
    for name, st in messengers.items():
        if st.get("enabled"):
            enabled_channels.append(name)
    return {
        "status": "ok" if secretary.ready() else "degraded",
        "service": "ava-text-bot",
        "role": "quantum-labs-secretary",
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "telegram_business_bot_configured": bool(TELEGRAM_BUSINESS_BOT_TOKEN),
        "telegram_business": biz,
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "mailer_base": AVA_MAILER_BASE,
        "knowledge_base": KNOWLEDGE_BASE,
        "owners_configured": len(b.owners),
        "scenarios": [s.id for s in list_scenarios("owner")],
        "channels": enabled_channels,
        "messengers": messengers,
        "endpoints": [
            "/api/chat",
            "/api/chat/reset",
            "/webhooks/whatsapp",
            "/webhooks/max",
            "/webhooks/vk",
            "/health",
        ],
        "tools": [t["function"]["name"] for t in OPENAI_TOOLS if t.get("type") == "function"],
    }
