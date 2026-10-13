"""Quantum Labs — text secretary for Telegram (shared brain with AVA phone)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field

from ava_client import OPENAI_TOOLS, run_tool
import max_client
from prompt_loader import greeting_text, load_system_prompt
from session_store import append_message, clear_chat, init_db, load_messages

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ava-text-bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
AVA_CONFIG_PATH = Path(os.getenv("AVA_CONFIG_PATH", "/root/ava/config/ai-agent.local.yaml"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
SESSION_DB = DATA_DIR / "sessions.db"
POLL_INTERVAL_S = float(os.getenv("TELEGRAM_POLL_INTERVAL_SECONDS", "1"))
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "6"))
WEBHOOK_TOKEN = os.getenv("WEBHOOK_TOKEN", "").strip()

app = FastAPI(title="AVA Text Bot")
_client: OpenAI | None = None
_system_prompt: str = ""
_greeting: str = ""
_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()


def _check_api_token(x_webhook_token: str | None) -> None:
    if not WEBHOOK_TOKEN:
        return
    if (x_webhook_token or "").strip() != WEBHOOK_TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")


class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    text: str = Field(..., min_length=1)
    channel: str = Field(default="api")


class ChatResetRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    channel: str = Field(default="api")


class MessengerSendRequest(BaseModel):
    channel: str = Field(..., description="telegram | max")
    text: str = Field(..., min_length=1)
    chat_id: str | None = None
    user_id: str | None = None



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
        {
            "chat_id": chat_id,
            "text": str(text)[:4096],
        },
        timeout=20.0,
    )


def _serialize_assistant_message(message: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant"}
    content = getattr(message, "content", None)
    if content:
        out["content"] = content
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ]
    return out


def generate_reply(chat_id: str, user_text: str) -> str:
    assert _client is not None
    append_message(SESSION_DB, chat_id, {"role": "user", "content": user_text})
    history = load_messages(SESSION_DB, chat_id)
    messages: list[dict[str, Any]] = [{"role": "system", "content": _system_prompt}]
    messages.extend(history)

    for _ in range(MAX_TOOL_ROUNDS):
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.4,
        )
        choice = response.choices[0].message
        assistant_msg = _serialize_assistant_message(choice)
        messages.append(assistant_msg)
        append_message(SESSION_DB, chat_id, assistant_msg)

        tool_calls = getattr(choice, "tool_calls", None) or []
        if not tool_calls:
            return str(choice.content or "Извините, не смог сформулировать ответ.").strip()

        for tc in tool_calls:
            fn = tc.function
            try:
                args = json.loads(fn.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = run_tool(fn.name, args, mailer_base=AVA_MAILER_BASE)
            tool_msg = {
                "role": "tool",
                "tool_call_id": tc.id,
                "name": fn.name,
                "content": result,
            }
            messages.append(tool_msg)
            append_message(SESSION_DB, chat_id, tool_msg)

    return "Сейчас не получается завершить запрос. Попробуйте переформулировать или напишите позже."


def handle_update(update: dict[str, Any]) -> None:
    message = update.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    if chat_id is None:
        return

    text = str(message.get("text") or "").strip()
    if not text:
        return

    if text in ("/start", "/help"):
        clear_chat(SESSION_DB, str(chat_id))
        send_telegram(chat_id, _greeting)
        append_message(SESSION_DB, str(chat_id), {"role": "assistant", "content": _greeting})
        return

    if text == "/reset":
        clear_chat(SESSION_DB, str(chat_id))
        send_telegram(chat_id, "Диалог сброшен. " + _greeting)
        append_message(SESSION_DB, str(chat_id), {"role": "assistant", "content": _greeting})
        return

    try:
        reply = generate_reply(str(chat_id), text)
        send_telegram(chat_id, reply)
    except Exception:
        logger.exception("handle message chat_id=%s", chat_id)
        send_telegram(
            chat_id,
            "Извините, произошла ошибка. Попробуйте ещё раз через минуту или позвоните на линию Quantum Labs.",
        )


def poll_loop() -> None:
    offset: int | None = None
    logger.info("Telegram poll loop started")
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
                    handle_update(upd)
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
    global _client, _system_prompt, _greeting, _poll_thread
    init_db(SESSION_DB)
    if not OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY missing")
    else:
        _client = OpenAI(api_key=OPENAI_API_KEY)
    _system_prompt = load_system_prompt(AVA_CONFIG_PATH)
    _greeting = greeting_text(AVA_CONFIG_PATH)
    if TELEGRAM_BOT_TOKEN:
        _poll_thread = threading.Thread(target=poll_loop, name="telegram-poll", daemon=True)
        _poll_thread.start()
        logger.info("bot ready model=%s mailer=%s", OPENAI_MODEL, AVA_MAILER_BASE)
    else:
        logger.error("TELEGRAM_BOT_TOKEN missing — poll loop not started")


@app.on_event("shutdown")
def on_shutdown() -> None:
    _stop_event.set()


@app.post("/api/chat")
def api_chat(
    req: ChatRequest,
    x_webhook_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """HTTP secretary entry for MCP / Bitrix / any client."""
    _check_api_token(x_webhook_token)
    if _client is None:
        raise HTTPException(status_code=503, detail="openai_not_ready")
    session_id = f"{req.channel}:{req.user_id}"
    try:
        reply = generate_reply(session_id, req.text)
    except Exception as exc:  # noqa: BLE001
        logger.exception("api_chat failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {
        "ok": True,
        "channel": req.channel,
        "user_id": req.user_id,
        "reply": reply,
    }


@app.post("/api/chat/reset")
def api_chat_reset(
    req: ChatResetRequest,
    x_webhook_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_webhook_token)
    session_id = f"{req.channel}:{req.user_id}"
    clear_chat(SESSION_DB, session_id)
    return {
        "ok": True,
        "channel": req.channel,
        "user_id": req.user_id,
        "reply": "Диалог сброшен. " + (_greeting or ""),
    }


@app.get("/api/messenger/status")
def api_messenger_status(
    x_webhook_token: str | None = Header(default=None),
) -> dict[str, Any]:
    _check_api_token(x_webhook_token)
    return {
        "ok": True,
        "telegram": {
            "configured": bool(TELEGRAM_BOT_TOKEN),
            "poll_enabled": bool(TELEGRAM_BOT_TOKEN and _poll_thread and _poll_thread.is_alive()),
        },
        "max": max_client.status(),
        "api_auth_required": bool(WEBHOOK_TOKEN),
    }


@app.post("/api/messenger/send")
def api_messenger_send(
    req: MessengerSendRequest,
    x_webhook_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Outbound message to Telegram or Max (for Grok/MCP control)."""
    _check_api_token(x_webhook_token)
    channel = (req.channel or "").strip().lower()
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text_required")

    if channel in {"telegram", "tg"}:
        chat_id = (req.chat_id or req.user_id or "").strip()
        if not chat_id:
            raise HTTPException(status_code=400, detail="chat_id_or_user_id_required")
        if not TELEGRAM_BOT_TOKEN:
            raise HTTPException(status_code=503, detail="telegram_not_configured")
        try:
            send_telegram(chat_id, text)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"telegram_send_failed: {exc}") from exc
        return {"ok": True, "channel": "telegram", "chat_id": chat_id}

    if channel == "max":
        if not max_client.enabled():
            raise HTTPException(status_code=503, detail="max_not_configured")
        try:
            raw = max_client.send_text(
                user_id=req.user_id,
                chat_id=req.chat_id,
                text=text,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return {"ok": True, "channel": "max", "result": raw}

    raise HTTPException(status_code=400, detail="channel must be telegram|max")


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if TELEGRAM_BOT_TOKEN and OPENAI_API_KEY and _client else "degraded",
        "service": "ava-text-bot",
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "max": max_client.status(),
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "mailer_base": AVA_MAILER_BASE,
        "endpoints": [
            "/api/chat",
            "/api/chat/reset",
            "/api/messenger/status",
            "/api/messenger/send",
            "/health",
        ],
    }
