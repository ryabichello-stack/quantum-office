"""Channel-agnostic Quantum Labs secretary dialogue core.

Transports (Telegram, HTTP API, Bitrix, etc.) only deliver messages.
All conversation memory and tool use live here.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from openai import OpenAI

from ava_client import OPENAI_TOOLS, run_tool
from prompt_loader import channel_overlay, greeting_text, load_system_prompt
from session_store import append_message, clear_chat, init_db, load_messages

logger = logging.getLogger("ava-secretary")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
AVA_CONFIG_PATH = Path(os.getenv("AVA_CONFIG_PATH", "/root/ava/config/ai-agent.local.yaml"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
SESSION_DB = DATA_DIR / "sessions.db"
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "6"))

_JOIN_URL_RE = re.compile(r"https://telemost\.yandex\.ru/j/\S+", re.I)


def session_key(channel: str, user_id: str) -> str:
    return f"{channel.strip().lower()}:{str(user_id).strip()}"


class Secretary:
    def __init__(self) -> None:
        self.client: OpenAI | None = None
        self.base_prompt: str = ""
        self.greeting: str = ""

    def startup(self, openai_api_key: str) -> None:
        init_db(SESSION_DB)
        if openai_api_key:
            self.client = OpenAI(api_key=openai_api_key)
        self.base_prompt = load_system_prompt(AVA_CONFIG_PATH)
        self.greeting = greeting_text(AVA_CONFIG_PATH)
        logger.info("secretary ready model=%s db=%s", OPENAI_MODEL, SESSION_DB)

    def ready(self) -> bool:
        return self.client is not None

    def reset(self, channel: str, user_id: str) -> str:
        key = session_key(channel, user_id)
        clear_chat(SESSION_DB, key)
        return self.greeting

    def handle(
        self,
        *,
        channel: str,
        user_id: str,
        text: str,
        reply_to: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Process one user message in any channel.
        reply_to: for telegram file delivery = chat_id; otherwise optional.
        """
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty_text", "reply": ""}

        key = session_key(channel, user_id)
        lowered = text.lower()

        if lowered in ("/start", "/help", "start", "help", "помощь"):
            clear_chat(SESSION_DB, key)
            append_message(SESSION_DB, key, {"role": "assistant", "content": self.greeting})
            return {"ok": True, "reply": self.greeting, "session": key, "reset": True}

        if lowered in ("/reset", "reset", "сброс"):
            msg = "Диалог сброшен. " + self.greeting
            clear_chat(SESSION_DB, key)
            append_message(SESSION_DB, key, {"role": "assistant", "content": msg})
            return {"ok": True, "reply": msg, "session": key, "reset": True}

        if not self.client:
            return {
                "ok": False,
                "error": "openai_missing",
                "reply": "Секретарь временно без AI. Попробуйте позже.",
                "session": key,
            }

        try:
            reply = self._generate(channel=channel, session=key, user_text=text, reply_to=reply_to)
            return {"ok": True, "reply": reply, "session": key}
        except Exception as exc:
            logger.exception("secretary handle failed session=%s", key)
            return {
                "ok": False,
                "error": str(exc),
                "reply": "Извините, произошла ошибка. Напишите /reset и попробуйте ещё раз.",
                "session": key,
            }

    def _serialize_assistant_message(self, message: Any) -> dict[str, Any]:
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

    @staticmethod
    def _extract_join_urls(tool_payloads: list[str]) -> list[str]:
        found: list[str] = []
        seen: set[str] = set()
        for raw in tool_payloads:
            urls: list[str] = []
            try:
                data = json.loads(raw)
            except Exception:
                data = None
            if isinstance(data, dict):
                for key in ("join_url", "telemost_join_url"):
                    val = str(data.get(key) or "").strip()
                    if val:
                        urls.append(val)
                msg = str(data.get("message") or "")
                urls.extend(_JOIN_URL_RE.findall(msg))
            urls.extend(_JOIN_URL_RE.findall(raw or ""))
            for url in urls:
                clean = url.rstrip(").,;")
                if clean and clean not in seen:
                    seen.add(clean)
                    found.append(clean)
        return found

    @classmethod
    def _ensure_links_in_reply(cls, reply: str, tool_payloads: list[str]) -> str:
        """If tools returned Telemost URLs but the model omitted them, append."""
        urls = cls._extract_join_urls(tool_payloads)
        if not urls:
            return reply
        text = (reply or "").strip()
        present_ids = {
            u.rstrip("/").rstrip(").,;").split("/")[-1]
            for u in _JOIN_URL_RE.findall(text)
        }
        missing = []
        for url in urls:
            cid = url.rstrip("/").split("/")[-1]
            if cid and cid not in present_ids:
                present_ids.add(cid)
                missing.append(url)
        if not missing:
            return text
        block = "\n".join(f"Ссылка на ВКС (Телемост): {u}" for u in missing)
        if text:
            return f"{text}\n\n{block}"
        return block

    def _generate(
        self,
        *,
        channel: str,
        session: str,
        user_text: str,
        reply_to: Optional[str],
    ) -> str:
        assert self.client is not None
        system = f"{self.base_prompt}\n{channel_overlay(channel)}\n"
        append_message(SESSION_DB, session, {"role": "user", "content": user_text})
        history = load_messages(SESSION_DB, session)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(history)
        tool_payloads: list[str] = []

        for _ in range(MAX_TOOL_ROUNDS):
            # gpt-5-mini rejects custom temperature
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=OPENAI_TOOLS,
                tool_choice="auto",
            )
            choice = response.choices[0].message
            assistant_msg = self._serialize_assistant_message(choice)
            messages.append(assistant_msg)
            append_message(SESSION_DB, session, assistant_msg)

            tool_calls = getattr(choice, "tool_calls", None) or []
            if not tool_calls:
                reply = str(choice.content or "Извините, не смог сформулировать ответ.").strip()
                reply = self._ensure_links_in_reply(reply, tool_payloads)
                # Persist the possibly enriched reply for session continuity.
                if messages and messages[-1].get("role") == "assistant":
                    messages[-1]["content"] = reply
                return reply

            for tc in tool_calls:
                fn = tc.function
                try:
                    args = json.loads(fn.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                logger.info("tool session=%s name=%s", session, fn.name)
                result = run_tool(
                    fn.name,
                    args,
                    mailer_base=AVA_MAILER_BASE,
                    telegram_chat_id=reply_to if channel == "telegram" else None,
                    channel=channel,
                )
                tool_payloads.append(result)
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": fn.name,
                    "content": result,
                }
                messages.append(tool_msg)
                append_message(SESSION_DB, session, tool_msg)

        return "Сейчас не получается завершить запрос. Попробуйте переформулировать или напишите позже."


secretary = Secretary()
