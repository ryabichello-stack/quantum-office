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
from fastapi import FastAPI
from openai import OpenAI

from ava_client import OPENAI_TOOLS, run_tool
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

app = FastAPI(title="AVA Text Bot")
_client: OpenAI | None = None
_system_prompt: str = ""
_greeting: str = ""
_poll_thread: threading.Thread | None = None
_stop_event = threading.Event()


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


def _safe_send(chat_id: str | int, text: str) -> None:
    try:
        send_telegram(chat_id, text)
    except Exception:
        logger.exception("send_telegram failed chat_id=%s", chat_id)


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
        # gpt-5-mini rejects custom temperature — omit it
        response = _client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
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
            logger.info("tool call chat_id=%s name=%s", chat_id, fn.name)
            result = run_tool(
                fn.name,
                args,
                mailer_base=AVA_MAILER_BASE,
                telegram_chat_id=chat_id,
            )
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

    logger.info("incoming chat_id=%s text=%r", chat_id, text[:120])

    if text in ("/start", "/help"):
        clear_chat(SESSION_DB, str(chat_id))
        _safe_send(chat_id, _greeting)
        append_message(SESSION_DB, str(chat_id), {"role": "assistant", "content": _greeting})
        return

    if text == "/reset":
        clear_chat(SESSION_DB, str(chat_id))
        msg = "Диалог сброшен. " + _greeting
        _safe_send(chat_id, msg)
        append_message(SESSION_DB, str(chat_id), {"role": "assistant", "content": msg})
        return

    if _client is None:
        _safe_send(chat_id, "Бот временно без AI (нет OPENAI_API_KEY). Попробуйте позже.")
        return

    try:
        reply = generate_reply(str(chat_id), text)
        _safe_send(chat_id, reply)
        logger.info("replied chat_id=%s chars=%s", chat_id, len(reply or ""))
    except Exception:
        logger.exception("handle message chat_id=%s", chat_id)
        _safe_send(
            chat_id,
            "Извините, произошла ошибка. Напишите /reset и попробуйте ещё раз.",
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


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if TELEGRAM_BOT_TOKEN and OPENAI_API_KEY and _client else "degraded",
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN),
        "openai_configured": bool(OPENAI_API_KEY),
        "model": OPENAI_MODEL,
        "mailer_base": AVA_MAILER_BASE,
        "tools": [
            "get_company_knowledge",
            "check_calendar",
            "suggest_calendar_slots",
            "create_calendar_event",
            "create_conference",
            "send_file",
        ],
    }
