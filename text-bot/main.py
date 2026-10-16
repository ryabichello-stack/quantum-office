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
import owner_alerts
import voice_stt
import channel_curate

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-text-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_BUSINESS_BOT_TOKEN = os.getenv("TELEGRAM_BUSINESS_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_BOT_TOKEN = os.getenv("TELEGRAM_CHANNEL_BOT_TOKEN", "").strip()
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
WEBHOOK_TOKEN = os.getenv("OFFICE_WEBHOOK_TOKEN", os.getenv("WEBHOOK_TOKEN", "")).strip()
POLL_INTERVAL_S = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1"))
TG_HANDLE_WORKERS = max(1, int(os.getenv("TELEGRAM_HANDLE_WORKERS", "4")))

app = FastAPI(title="Quantum Labs Secretary", version="0.3.0")
_poll_thread: threading.Thread | None = None
_business_poll_thread: threading.Thread | None = None
_curate_poll_thread: threading.Thread | None = None
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
# Messenger MCP API (read + send Telegram / Max)
# --------------------


class MessengerSendRequest(BaseModel):
    channel: str = Field(..., description="telegram | max | tg | telegram_business")
    text: str = Field(..., min_length=1, max_length=4000)
    chat_id: Optional[str] = None
    user_id: Optional[str] = None
    business_connection_id: Optional[str] = None
    record_history: bool = Field(
        default=True,
        description="Append outbound text to local session history for later read",
    )


def _session_db():
    from secretary import SESSION_DB

    return SESSION_DB


def _resolve_session_id(
    *,
    session_id: Optional[str] = None,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> str:
    if session_id and str(session_id).strip():
        return str(session_id).strip()
    uid = (user_id or chat_id or "").strip()
    ch = (channel or "").strip().lower()
    if ch in {"tg"}:
        ch = "telegram"
    if not ch or not uid:
        raise HTTPException(
            status_code=400,
            detail="session_id or channel+user_id/chat_id required",
        )
    return f"{ch}:{uid}"


@app.get("/api/messenger/status")
def api_messenger_status(x_webhook_token: Optional[str] = Header(None)) -> dict[str, Any]:
    _check_api_token(x_webhook_token)
    biz = telegram_business.status()
    return {
        "ok": True,
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN),
            "poll_enabled": bool(
                TELEGRAM_BOT_TOKEN and _poll_thread and _poll_thread.is_alive()
            ),
        },
        "telegram_channel": {
            "configured": bool(TELEGRAM_CHANNEL_BOT_TOKEN and TELEGRAM_CHANNEL_ID),
            "channel_id": TELEGRAM_CHANNEL_ID or None,
        },
        "telegram_curate": channel_curate.status(),
        "telegram_business": biz,
        "max": max_messenger.status(),
        "api_auth_required": bool(WEBHOOK_TOKEN),
        "capabilities": {
            "send": True,
            "channel_publish": bool(TELEGRAM_CHANNEL_BOT_TOKEN and TELEGRAM_CHANNEL_ID),
            "session_history": True,
            "list_chats": True,
            "max_native_messages": True,
            "note": (
                "Telegram history = local secretary sessions (bot cannot scrape full TG history). "
                "Max native GET /messages needs admin + read_all_messages. "
                "News channel: POST /api/messenger/channel/publish."
            ),
        },
    }


@app.get("/api/messenger/chats")
def api_messenger_chats(
    channel: Optional[str] = None,
    limit: int = 50,
    x_webhook_token: Optional[str] = Header(None),
) -> dict[str, Any]:
    """List recent dialogue sessions (telegram:…, max:…, telegram_business:…)."""
    from session_store import list_sessions

    _check_api_token(x_webhook_token)
    ch = (channel or "").strip().lower() or None
    if ch == "tg":
        ch = "telegram"
    sessions = list_sessions(_session_db(), channel=ch, limit=limit)
    return {"ok": True, "count": len(sessions), "chats": sessions}


@app.get("/api/messenger/history")
def api_messenger_history(
    session_id: Optional[str] = None,
    channel: Optional[str] = None,
    user_id: Optional[str] = None,
    chat_id: Optional[str] = None,
    limit: int = 40,
    include_tools: bool = False,
    x_webhook_token: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Read local secretary conversation history for a Telegram/Max/API session."""
    from session_store import load_history

    _check_api_token(x_webhook_token)
    sid = _resolve_session_id(
        session_id=session_id, channel=channel, user_id=user_id, chat_id=chat_id
    )
    messages = load_history(
        _session_db(),
        sid,
        limit=max(1, min(int(limit or 40), 200)),
        include_tools=bool(include_tools),
    )
    ch = sid.split(":", 1)[0] if ":" in sid else None
    uid = sid.split(":", 1)[1] if ":" in sid else sid
    return {
        "ok": True,
        "session_id": sid,
        "channel": ch,
        "user_id": uid,
        "count": len(messages),
        "messages": messages,
        "source": "session",
    }


@app.get("/api/messenger/messages")
def api_messenger_messages(
    channel: str = "max",
    chat_id: Optional[str] = None,
    message_ids: Optional[str] = None,
    count: int = 50,
    from_ts: Optional[int] = None,
    to_ts: Optional[int] = None,
    x_webhook_token: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Native platform message fetch (currently Max GET /messages)."""
    _check_api_token(x_webhook_token)
    ch = (channel or "max").strip().lower()
    if ch != "max":
        raise HTTPException(
            status_code=400,
            detail="native messages only for channel=max; use /api/messenger/history for telegram",
        )
    if not max_messenger.enabled():
        raise HTTPException(status_code=503, detail="max_not_configured")
    try:
        raw = max_messenger.get_messages(
            chat_id=chat_id,
            message_ids=message_ids,
            count=count,
            from_ts=from_ts,
            to_ts=to_ts,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    messages = raw.get("messages") if isinstance(raw, dict) else None
    return {
        "ok": True,
        "channel": "max",
        "chat_id": chat_id,
        "count": len(messages) if isinstance(messages, list) else None,
        "messages": messages if messages is not None else raw,
        "source": "max_api",
    }


@app.post("/api/messenger/send")
def api_messenger_send(
    req: MessengerSendRequest,
    x_webhook_token: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Outbound message to Telegram or Max (for Grok/MCP)."""
    from session_store import append_message

    _check_api_token(x_webhook_token)
    channel = (req.channel or "").strip().lower()
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text_required")

    if channel in {"telegram", "tg", "telegram_business"}:
        chat = (req.chat_id or req.user_id or "").strip()
        if not chat:
            raise HTTPException(status_code=400, detail="chat_id_or_user_id_required")
        use_business = channel == "telegram_business" or bool(req.business_connection_id)
        if use_business:
            if not (TELEGRAM_BUSINESS_BOT_TOKEN or TELEGRAM_BOT_TOKEN):
                raise HTTPException(status_code=503, detail="telegram_business_not_configured")
            token = _business_token()
            conn_id = (req.business_connection_id or "").strip() or None
            if not conn_id:
                # Best-effort: first known business connection
                conns = telegram_business.list_connections()
                if conns:
                    conn_id = str(conns[0].get("id") or "") or None
            try:
                send_telegram(
                    chat, text, business_connection_id=conn_id, token=token
                )
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502, detail=f"telegram_business_send_failed: {exc}"
                ) from exc
            hist_channel = "telegram_business"
        else:
            if not TELEGRAM_BOT_TOKEN:
                raise HTTPException(status_code=503, detail="telegram_not_configured")
            try:
                send_telegram(chat, text)
            except Exception as exc:  # noqa: BLE001
                raise HTTPException(
                    status_code=502, detail=f"telegram_send_failed: {exc}"
                ) from exc
            hist_channel = "telegram"
        if req.record_history:
            sid = f"{hist_channel}:{chat}"
            append_message(
                _session_db(),
                sid,
                {"role": "assistant", "content": text},
            )
        return {
            "ok": True,
            "channel": hist_channel,
            "chat_id": chat,
            "session_id": f"{hist_channel}:{chat}",
        }

    if channel == "max":
        if not max_messenger.enabled():
            raise HTTPException(status_code=503, detail="max_not_configured")
        try:
            raw = max_messenger.send_text(
                user_id=req.user_id,
                chat_id=req.chat_id,
                text=text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        peer = (req.user_id or req.chat_id or "").strip()
        if req.record_history and peer:
            append_message(
                _session_db(),
                f"max:{peer}",
                {"role": "assistant", "content": text},
            )
        return {
            "ok": True,
            "channel": "max",
            "user_id": req.user_id,
            "chat_id": req.chat_id,
            "session_id": f"max:{peer}" if peer else None,
            "result": raw,
        }

    raise HTTPException(status_code=400, detail="channel must be telegram|max|telegram_business")


class ChannelPublishRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4096)
    channel_id: Optional[str] = Field(
        default=None,
        description="Override TELEGRAM_CHANNEL_ID (@name or -100…)",
    )
    parse_mode: Optional[str] = Field(
        default=None,
        description="HTML | Markdown | MarkdownV2 (optional)",
    )
    disable_notification: bool = False
    disable_web_page_preview: bool = False


@app.post("/api/messenger/channel/publish")
def api_messenger_channel_publish(
    req: ChannelPublishRequest,
    x_webhook_token: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Publish a news post to the configured Telegram channel (bot must be admin)."""
    _check_api_token(x_webhook_token)
    token = TELEGRAM_CHANNEL_BOT_TOKEN or TELEGRAM_BOT_TOKEN
    chat = (req.channel_id or TELEGRAM_CHANNEL_ID or "").strip()
    text = (req.text or "").strip()
    if not token:
        raise HTTPException(status_code=503, detail="telegram_channel_not_configured")
    if not chat:
        raise HTTPException(status_code=400, detail="channel_id_required")
    if not text:
        raise HTTPException(status_code=400, detail="text_required")

    payload: dict[str, Any] = {
        "chat_id": chat,
        "text": text[:4096],
        "disable_notification": bool(req.disable_notification),
        "disable_web_page_preview": bool(req.disable_web_page_preview),
    }
    pm = (req.parse_mode or "").strip()
    if pm:
        payload["parse_mode"] = pm

    try:
        raw = _tg_post("sendMessage", payload, token=token, timeout=20.0)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502, detail=f"telegram_channel_publish_failed: {exc}"
        ) from exc

    result = raw.get("result") if isinstance(raw, dict) else None
    message_id = result.get("message_id") if isinstance(result, dict) else None
    return {
        "ok": bool(raw.get("ok")) if isinstance(raw, dict) else True,
        "channel_id": chat,
        "message_id": message_id,
        "result": result,
    }


# --------------------
# Owner alerts (Telegram + Max fan-out)
# --------------------


class OwnerAlertRequest(BaseModel):
    kind: str = Field(
        ...,
        description="outreach_reply|new_chat|inbound_call|form_callback",
        min_length=1,
        max_length=80,
    )
    title: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=4000)
    meta: Optional[dict[str, Any]] = None
    dedupe_key: Optional[str] = Field(default=None, max_length=400)


class FormCallbackRequest(BaseModel):
    """Website / Bitrix «заказать звонок» → owner Telegram + Max."""

    name: str = Field(default="", max_length=200)
    phone: str = Field(default="", max_length=80)
    email: str = Field(default="", max_length=200)
    company: str = Field(default="", max_length=300)
    comment: str = Field(default="", max_length=2000)
    source: str = Field(default="website", max_length=120)
    page: str = Field(default="", max_length=500)


@app.post("/api/owner-alert")
def api_owner_alert(req: OwnerAlertRequest, x_webhook_token: Optional[str] = Header(None)):
    _check_api_token(x_webhook_token)
    return owner_alerts.notify_owner(
        kind=req.kind,
        title=req.title,
        body=req.body,
        meta=req.meta,
        dedupe_key=req.dedupe_key,
    )


@app.post("/api/owner-alert/form")
def api_owner_alert_form(
    req: FormCallbackRequest, x_webhook_token: Optional[str] = Header(None)
):
    """Ingest callback / lead form → notify owner in Telegram and Max."""
    _check_api_token(x_webhook_token)
    lines = []
    if req.name:
        lines.append(f"Имя: {req.name}")
    if req.phone:
        lines.append(f"Телефон: {req.phone}")
    if req.email:
        lines.append(f"Email: {req.email}")
    if req.company:
        lines.append(f"Компания: {req.company}")
    if req.source:
        lines.append(f"Источник: {req.source}")
    if req.page:
        lines.append(f"Страница: {req.page}")
    if req.comment:
        lines.append("")
        lines.append(req.comment)
    if not lines:
        lines.append("(пустая заявка)")
    dedupe = "|".join(
        [
            "form",
            (req.phone or "").strip(),
            (req.email or "").strip().lower(),
            (req.name or "").strip().lower()[:80],
            (req.comment or "").strip()[:80],
        ]
    )
    return owner_alerts.notify_owner(
        kind="form_callback",
        title=req.company or req.name or req.phone or "форма",
        body="\n".join(lines),
        meta={
            "phone": req.phone,
            "email": req.email,
            "company": req.company,
            "source": req.source,
            "from": req.name,
        },
        dedupe_key=dedupe if (req.phone or req.email or req.comment) else None,
    )


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


def _force_ipv4_telegram() -> None:
    """Telegram IPv6 from this host is often unreachable; prefer A records."""
    import socket

    if getattr(socket, "_ql_ipv4_telegram", False):
        return
    _orig = socket.getaddrinfo

    def _getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):  # noqa: A002
        h = (host or "").lower()
        if h in {"api.telegram.org", "telegram.org"} or h.endswith(".telegram.org"):
            return _orig(host, port, socket.AF_INET, type, proto, flags)
        return _orig(host, port, family, type, proto, flags)

    socket.getaddrinfo = _getaddrinfo  # type: ignore[assignment]
    socket._ql_ipv4_telegram = True  # type: ignore[attr-defined]


def _tg_post(
    method: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    _force_ipv4_telegram()
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


def _resolve_incoming_text(
    *,
    message: dict[str, Any],
    text: str,
    token: str,
    chat_id: str | int,
    business_connection_id: str | None = None,
) -> str | None:
    """Prefer explicit text; otherwise STT from voice/audio. None = nothing to handle."""
    text = (text or "").strip()
    if text:
        return text
    voice = voice_stt.extract_voice_file(message)
    if not voice:
        return None
    if not voice_stt.enabled():
        _safe_send(
            chat_id,
            "Голосовые сейчас недоступны — напишите текстом, пожалуйста.",
            business_connection_id=business_connection_id,
            token=token,
        )
        return None
    if not OPENAI_API_KEY:
        _safe_send(
            chat_id,
            "Не удалось распознать голос. Напишите текстом, пожалуйста.",
            business_connection_id=business_connection_id,
            token=token,
        )
        return None
    try:
        _safe_typing(chat_id, business_connection_id=business_connection_id, token=token)
        transcript = voice_stt.transcribe_telegram_voice(
            token=token,
            file_id=voice["file_id"],
            openai_api_key=OPENAI_API_KEY,
        )
        return voice_stt.format_voice_user_text(transcript, kind=voice.get("kind") or "voice")
    except Exception:
        logger.exception("voice stt failed chat_id=%s", chat_id)
        _safe_send(
            chat_id,
            "Не расслышал голосовое — напишите текстом или повторите, пожалуйста.",
            business_connection_id=business_connection_id,
            token=token,
        )
        return None


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
    message = parsed.get("message") or {}

    conn = telegram_business.get_connection(conn_id)
    owner_id = str((conn or {}).get("user_id") or "")

    # Owner typed from the phone → pause auto-reply so we don't talk over them.
    if owner_id and user_id == owner_id:
        telegram_business.pause_chat(chat_id)
        logger.info("business owner message chat_id=%s — auto-reply paused", chat_id)
        return

    if not telegram_business.auto_reply_enabled():
        logger.info("business auto-reply disabled; skip chat_id=%s", chat_id)
        return
    if telegram_business.is_paused(chat_id):
        logger.info("business chat paused chat_id=%s — skip", chat_id)
        return
    if conn and not conn.get("is_enabled", True):
        return

    text = _resolve_incoming_text(
        message=message if isinstance(message, dict) else {},
        text=text,
        token=biz_tok,
        chat_id=chat_id,
        business_connection_id=conn_id,
    )
    if not text:
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
        business_connection_id=conn_id,
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
    text = str(message.get("text") or message.get("caption") or "").strip()
    chat_type = str(chat.get("type") or "private")
    user_id = str(from_user.get("id") or chat_id)
    tok = token or TELEGRAM_BOT_TOKEN

    text = _resolve_incoming_text(
        message=message if isinstance(message, dict) else {},
        text=text,
        token=tok,
        chat_id=chat_id,
    )
    if not text:
        return

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


def _handle_curate_update_safe(update: dict[str, Any]) -> None:
    try:
        channel_curate.handle_update(
            update,
            tg_post=_tg_post,
            openai_api_key=OPENAI_API_KEY,
            model=OPENAI_MODEL,
        )
    except Exception:
        logger.exception("curate update failed: %s", update.get("update_id"))


def poll_loop(
    *,
    token: str,
    name: str,
    allow_direct_messages: bool = True,
    allowed_updates: list[str] | None = None,
    on_update=None,
) -> None:
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

    if allowed_updates is not None:
        allowed = list(allowed_updates)
    else:
        allowed = [
            "business_connection",
            "business_message",
            "edited_business_message",
        ]
        if allow_direct_messages:
            allowed.insert(0, "message")

    handler = on_update or (lambda upd: _handle_update_safe(upd, token=token))

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
                _update_pool.submit(handler, upd)
        except urllib.error.URLError as exc:
            logger.warning("poll error name=%s: %s", name, exc)
            time.sleep(3)
        except Exception:
            logger.exception("poll unexpected name=%s", name)
            time.sleep(3)
        time.sleep(POLL_INTERVAL_S)


@app.on_event("startup")
def on_startup() -> None:
    global _poll_thread, _business_poll_thread, _curate_poll_thread
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

    # News curate bot (forward → rewrite → @epoch_z): separate token poller
    curate_tok = TELEGRAM_CHANNEL_BOT_TOKEN
    if channel_curate.enabled() and curate_tok:
        same_personal = curate_tok == TELEGRAM_BOT_TOKEN
        same_business = bool(TELEGRAM_BUSINESS_BOT_TOKEN) and curate_tok == TELEGRAM_BUSINESS_BOT_TOKEN
        if same_personal or same_business:
            logger.warning(
                "TELEGRAM_CHANNEL_BOT_TOKEN coincides with secretary bot — "
                "curate poller skipped (use a dedicated channel bot token)"
            )
        else:
            _curate_poll_thread = threading.Thread(
                target=poll_loop,
                kwargs={
                    "token": curate_tok,
                    "name": "channel-curate",
                    "allowed_updates": ["message", "callback_query"],
                    "on_update": _handle_curate_update_safe,
                },
                name="telegram-curate-poll",
                daemon=True,
            )
            _curate_poll_thread.start()
            logger.info(
                "telegram channel curate poller enabled target=%s",
                channel_curate.target_channel(),
            )
    else:
        logger.info("channel curate poller off")

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
    import training as training_mod

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
        "telegram_channel_configured": bool(
            TELEGRAM_CHANNEL_BOT_TOKEN and TELEGRAM_CHANNEL_ID
        ),
        "telegram_channel_id": TELEGRAM_CHANNEL_ID or None,
        "telegram_curate": channel_curate.status(),
        "telegram_business": biz,
        "voice_stt": voice_stt.enabled(),
        "owner_alerts": owner_alerts.status(),
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "mailer_base": AVA_MAILER_BASE,
        "knowledge_base": KNOWLEDGE_BASE,
        "owners_configured": len(b.owners),
        "training": {
            "enabled": training_mod.training_enabled(),
            "pin_configured": training_mod.pin_configured(),
            "allowlist": len(training_mod.trainee_allowlist()),
        },
        "scenarios": [s.id for s in list_scenarios("owner")],
        "trainee_scenarios": [s.id for s in list_scenarios("trainee")],
        "channels": enabled_channels,
        "messengers": messengers,
        "endpoints": [
            "/api/chat",
            "/api/chat/reset",
            "/api/messenger/status",
            "/api/messenger/chats",
            "/api/messenger/history",
            "/api/messenger/messages",
            "/api/messenger/send",
            "/api/messenger/channel/publish",
            "/webhooks/whatsapp",
            "/webhooks/max",
            "/webhooks/vk",
            "/health",
        ],
        "tools": [t["function"]["name"] for t in OPENAI_TOOLS if t.get("type") == "function"],
    }
