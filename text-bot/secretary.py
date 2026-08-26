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

from agent_loop import looks_like_stall
from ava_client import tools_for_role, run_tool
from prompt_loader import channel_overlay, greeting_text, load_system_prompt
from scenarios import (
    detect_scenario,
    format_scenarios_help,
    get_scenario,
    load_scenarios,
    looks_like_outbound_request,
    parse_scenario_command,
    role_for,
    scenario_overlay,
)
from session_store import (
    append_message,
    clear_chat,
    get_session_meta,
    init_db,
    load_messages,
    set_session_scenario,
)

logger = logging.getLogger("ava-secretary")

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
AVA_MAILER_BASE = os.getenv("AVA_MAILER_BASE", "http://127.0.0.1:8000").strip()
AVA_CONFIG_PATH = Path(os.getenv("AVA_CONFIG_PATH", "/root/ava/config/ai-agent.local.yaml"))
DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/ava-text-bot/data"))
SESSION_DB = DATA_DIR / "sessions.db"
MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "14"))

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
        load_scenarios()
        if openai_api_key:
            self.client = OpenAI(api_key=openai_api_key)
        self.base_prompt = load_system_prompt(AVA_CONFIG_PATH)
        self.greeting = greeting_text(AVA_CONFIG_PATH)
        logger.info("secretary ready model=%s db=%s", OPENAI_MODEL, SESSION_DB)

    def ready(self) -> bool:
        return self.client is not None

    def reset(self, channel: str, user_id: str, *, chat_type: str | None = None) -> str:
        key = session_key(channel, user_id)
        clear_chat(SESSION_DB, key)
        role = role_for(user_id, channel, chat_type=chat_type)
        return greeting_text(AVA_CONFIG_PATH, role=role)

    def handle(
        self,
        *,
        channel: str,
        user_id: str,
        text: str,
        reply_to: Optional[str] = None,
        scenario: Optional[str] = None,
        chat_type: Optional[str] = None,
        business_connection_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Process one user message in any channel.
        reply_to: for telegram file delivery = chat_id; otherwise optional.
        scenario: optional hard override for this turn (API).
        chat_type: telegram chat type (private|group|supergroup|channel).
        business_connection_id: Telegram Business connection for sendDocument-as-account.
        """
        text = (text or "").strip()
        if not text:
            return {"ok": False, "error": "empty_text", "reply": ""}

        key = session_key(channel, user_id)
        role = role_for(user_id, channel, chat_type=chat_type)
        lowered = text.lower()
        meta = get_session_meta(SESSION_DB, key)
        sticky = bool(meta.get("sticky"))
        sticky_id = meta.get("scenario") if sticky else None

        if lowered in ("/start", "/help", "start", "help", "помощь"):
            clear_chat(SESSION_DB, key)
            greet = greeting_text(AVA_CONFIG_PATH, role=role)
            help_extra = (
                "\n\nЯ ваш личный секретарь. Команды режимов: /режимы"
                if role == "owner"
                else "\n\nКоманды: /режимы"
            )
            reply = greet + help_extra
            append_message(SESSION_DB, key, {"role": "assistant", "content": reply})
            return {
                "ok": True,
                "reply": reply,
                "session": key,
                "reset": True,
                "role": role,
                "scenario": sticky_id or ("secretary" if role == "owner" else "office"),
            }

        if lowered in ("/reset", "reset", "сброс"):
            msg = "Диалог сброшен. " + greeting_text(AVA_CONFIG_PATH, role=role)
            clear_chat(SESSION_DB, key)
            append_message(SESSION_DB, key, {"role": "assistant", "content": msg})
            return {
                "ok": True,
                "reply": msg,
                "session": key,
                "reset": True,
                "role": role,
                "scenario": sticky_id or ("secretary" if role == "owner" else "office"),
            }

        # Scenario commands
        action, payload = parse_scenario_command(text, role)
        if action == "list":
            current = sticky_id or (scenario or ("secretary" if role == "owner" else "office"))
            reply = format_scenarios_help(role, current, sticky)
            append_message(SESSION_DB, key, {"role": "user", "content": text})
            append_message(SESSION_DB, key, {"role": "assistant", "content": reply})
            return {
                "ok": True,
                "reply": reply,
                "session": key,
                "role": role,
                "scenario": current,
                "sticky": sticky,
            }
        if action == "set" and payload:
            set_session_scenario(SESSION_DB, key, payload, sticky=True)
            sc = get_scenario(payload)
            title = sc.title if sc else payload
            reply = f"Ок, режим закреплён: {payload} — {title}.\nСброс: /режим сброс"
            append_message(SESSION_DB, key, {"role": "user", "content": text})
            append_message(SESSION_DB, key, {"role": "assistant", "content": reply})
            return {
                "ok": True,
                "reply": reply,
                "session": key,
                "role": role,
                "scenario": payload,
                "sticky": True,
            }
        if action == "clear":
            set_session_scenario(SESSION_DB, key, None, sticky=False)
            reply = "Режим сброшен — снова выбираю сценарий автоматически."
            append_message(SESSION_DB, key, {"role": "user", "content": text})
            append_message(SESSION_DB, key, {"role": "assistant", "content": reply})
            return {
                "ok": True,
                "reply": reply,
                "session": key,
                "role": role,
                "scenario": "secretary" if role == "owner" else "office",
                "sticky": False,
            }
        if action == "unknown":
            reply = f"Не знаю режим «{payload}». Напишите /режимы"
            return {"ok": False, "error": "unknown_scenario", "reply": reply, "session": key}

        # Resolve active scenario for this turn.
        # Outbound call requests always win over sticky memory/secretary — otherwise
        # the model may parrot Second Brain rules instead of drafting a call script.
        if scenario and get_scenario(scenario):
            active = get_scenario(scenario)
            sticky_now = False
        elif role == "owner" and looks_like_outbound_request(text) and get_scenario("outbound"):
            active = get_scenario("outbound")
            sticky_now = False
            set_session_scenario(SESSION_DB, key, "outbound", sticky=False)
        elif sticky and sticky_id and get_scenario(sticky_id):
            active = get_scenario(sticky_id)
            sticky_now = True
        else:
            active = detect_scenario(text, role)
            sticky_now = False
            # remember last auto scenario (non-sticky) for continuity hints
            set_session_scenario(SESSION_DB, key, active.id if active else None, sticky=False)

        if not self.client:
            return {
                "ok": False,
                "error": "openai_missing",
                "reply": "Секретарь временно без AI. Попробуйте позже.",
                "session": key,
                "role": role,
                "scenario": active.id if active else None,
            }

        try:
            reply = self._generate(
                channel=channel,
                session=key,
                user_text=text,
                reply_to=reply_to,
                role=role,
                scenario_id=active.id if active else "secretary",
                sticky=sticky_now,
                business_connection_id=business_connection_id,
            )
            return {
                "ok": True,
                "reply": reply,
                "session": key,
                "role": role,
                "scenario": active.id if active else None,
                "sticky": sticky_now,
            }
        except Exception as exc:
            logger.exception("secretary handle failed session=%s", key)
            return {
                "ok": False,
                "error": str(exc),
                "reply": "Извините, произошла ошибка. Напишите /reset и попробуйте ещё раз.",
                "session": key,
                "role": role,
                "scenario": active.id if active else None,
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

    @staticmethod
    def _extract_owner_messages(tool_payloads: list[str]) -> list[str]:
        found: list[str] = []
        for raw in tool_payloads:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            msg = str(data.get("owner_message") or "").strip()
            if msg:
                found.append(msg)
        return found

    @classmethod
    def _ensure_owner_messages_in_reply(cls, reply: str, tool_payloads: list[str]) -> str:
        """If a tool built owner_message (draft/files) but the model omitted it, send it."""
        owner_msgs = cls._extract_owner_messages(tool_payloads)
        if not owner_msgs:
            return reply
        owner = owner_msgs[-1]
        text = (reply or "").strip()

        # Outbound draft: must include Greeting + Script, not a teaser line.
        if "Greeting:" in owner and "Script:" in owner:
            if "Greeting:" in text and "Script:" in text:
                return text
            return owner

        # Files browse/search: must include the formatted list.
        if ("Папки:" in owner or "Файлы:" in owner or "Поиск:" in owner) and not (
            "Папки:" in text or "Файлы:" in text or "Поиск:" in text or "•" in text
        ):
            return owner

        # Email send confirmation.
        if "Письмо поставлено в очередь" in owner and "Письмо поставлено" not in text:
            if text:
                return f"{text}\n\n{owner}"
            return owner

        if not text:
            return owner
        return text

    def _generate(
        self,
        *,
        channel: str,
        session: str,
        user_text: str,
        reply_to: Optional[str],
        role: str,
        scenario_id: str,
        sticky: bool,
        business_connection_id: Optional[str] = None,
    ) -> str:
        assert self.client is not None
        sc = get_scenario(scenario_id)
        overlay = scenario_overlay(sc, role=role, sticky=sticky) if sc else ""
        system = (
            f"{self.base_prompt}\n"
            f"{channel_overlay(channel, role=role)}\n"
            f"{overlay}\n"
        )
        append_message(SESSION_DB, session, {"role": "user", "content": user_text})
        history = load_messages(SESSION_DB, session)
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        messages.extend(history)
        tool_payloads: list[str] = []
        tools_used = 0
        continue_nudges = 0
        tg_channels = {"telegram", "telegram_business"}
        tg_chat_id = reply_to if (channel or "").strip().lower() in tg_channels else None

        for round_i in range(MAX_TOOL_ROUNDS):
            # gpt-5-mini rejects custom temperature
            response = self.client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=messages,
                tools=tools_for_role(role),
                tool_choice="auto",
            )
            choice = response.choices[0].message
            assistant_msg = self._serialize_assistant_message(choice)
            messages.append(assistant_msg)
            append_message(SESSION_DB, session, assistant_msg)

            tool_calls = getattr(choice, "tool_calls", None) or []
            if tool_calls:
                for tc in tool_calls:
                    fn = tc.function
                    try:
                        args = json.loads(fn.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    logger.info(
                        "tool session=%s scenario=%s round=%s name=%s",
                        session,
                        scenario_id,
                        round_i,
                        fn.name,
                    )
                    # Interim message before long-running tools.
                    if fn.name == "outbound_dial" and reply_to and channel == "telegram":
                        phone_val = args.get("phone") or ""
                        from main import _safe_send
                        _safe_send(
                            reply_to,
                            f"⏳ Набираю {phone_val}… Жду результат (до 1.5 мин).",
                        )
                    elif fn.name == "await_outbound_result" and reply_to and channel == "telegram":
                        from main import _safe_typing
                        _safe_typing(reply_to)

                    result = run_tool(
                        fn.name,
                        args,
                        mailer_base=AVA_MAILER_BASE,
                        telegram_chat_id=tg_chat_id,
                        business_connection_id=business_connection_id,
                        channel=channel,
                        role=role,
                    )
                    tools_used += 1
                    tool_payloads.append(result)
                    # Nudge inside tool payload so the model keeps chaining if needed
                    try:
                        payload = json.loads(result)
                        if isinstance(payload, dict):
                            payload.setdefault(
                                "next_step_hint",
                                (
                                    "Если задача ещё не решена — сам вызови следующий tool "
                                    "с уточнённым запросом. Меню «как искать» запрещено. "
                                    "Если после своих попыток не хватает конкретного факта "
                                    "(ИНН/ФИО/email/период/кого из найденных) — задай "
                                    "ОДИН короткий уточняющий вопрос пользователю."
                                ),
                            )
                            result = json.dumps(payload, ensure_ascii=False)
                    except json.JSONDecodeError:
                        pass
                    tool_msg = {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fn.name,
                        "content": result,
                    }
                    messages.append(tool_msg)
                    append_message(SESSION_DB, session, tool_msg)
                continue

            reply = str(choice.content or "Извините, не смог сформулировать ответ.").strip()
            reply = self._ensure_owner_messages_in_reply(reply, tool_payloads)
            reply = self._ensure_links_in_reply(reply, tool_payloads)

            # Agentic continue: block search-method menus; allow one concrete clarify ask
            if (
                role == "owner"
                and looks_like_stall(reply)
                and continue_nudges < 3
                and round_i < MAX_TOOL_ROUNDS - 1
            ):
                continue_nudges += 1
                logger.info(
                    "stall-nudge session=%s round=%s tools_used=%s",
                    session,
                    round_i,
                    tools_used,
                )
                if tools_used >= 2:
                    nudge = (
                        "[internal — не показывай пользователю] "
                        "Запрещено меню «как/где искать». Либо вызови ещё один tool "
                        "с уточнённым запросом по уже найденным данным, либо задай "
                        "пользователю ОДИН конкретный вопрос о недостающем факте "
                        "(ИНН, полное ФИО, email, период, кого/какую из найденных). "
                        "Не предлагай варианты способов поиска."
                    )
                else:
                    nudge = (
                        "[internal — не показывай пользователю] "
                        "Запрещено спрашивать, как искать или предлагать меню вариантов. "
                        "Сам вызови tool (search_office_memory / find_office_contact / "
                        "list_office_threads) с уточнённым запросом. Если после попыток "
                        "не хватит факта — тогда один точный вопрос пользователю."
                    )
                messages.append({"role": "user", "content": nudge})
                continue

            if messages and messages[-1].get("role") == "assistant":
                messages[-1]["content"] = reply
            return reply

        return "Сейчас не получается завершить запрос. Попробуйте переформулировать или напишите позже."


secretary = Secretary()
