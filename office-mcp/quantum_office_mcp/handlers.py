"""Tool handlers for Quantum Office MCP."""

from __future__ import annotations

import json
from typing import Any

from quantum_office_mcp.client import (
    calendar_base,
    calendar_request,
    campaign_base,
    campaign_request,
    conference_base,
    conference_request,
    console_base,
    console_request,
    files_base,
    files_request,
    health_probe,
    knowledge_base,
    knowledge_request,
    mailer_base,
    outreach_base,
    outreach_request,
    text_bot_base,
    text_bot_request,
)
from quantum_office_mcp.script_builder import build_task_prompt


def _tool_result(payload: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, indent=2)
    out: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        out["isError"] = True
    return out


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _dial(args: dict[str, Any]) -> dict[str, Any]:
    """Originate via Console /api/outbound/dial (auto: callback if API live, else SIP)."""
    phone = (args.get("phone") or "").strip()
    if not phone:
        return _tool_result({"ok": False, "error": "phone required"}, is_error=True)

    body: dict[str, Any] = {
        "phone": phone,
        "mode": (args.get("mode") or "auto").strip() or "auto",
        "context": args.get("context") or "outbound",
        "wait_progress_sec": float(args.get("wait_progress_sec") or 12),
    }
    for key in (
        "greeting",
        "script",
        "provider",
        "caller_id_num",
        "caller_id_name",
    ):
        if args.get(key) is not None and str(args.get(key)).strip() != "":
            body[key] = args[key]
    if isinstance(args.get("tools"), list):
        body["tools"] = args["tools"]
    if "use_knowledge" in args:
        body["use_knowledge"] = _as_bool(args.get("use_knowledge"))
    dial = console_request("POST", "/api/outbound/dial", body, timeout=60)
    return _tool_result(
        {
            "ok": bool(dial.get("ok")),
            "mode": dial.get("mode"),
            "phone": phone,
            "dial": dial,
            "note": dial.get("note")
            or (
                "Console dial: auto выбирает Mango callback (если API live) "
                "или SIP/ARI с IP 45.147.178.172. Успех = мобильный звонит."
            ),
        }
    )


def _assign_task(args: dict[str, Any]) -> dict[str, Any]:
    phone = (args.get("phone") or "").strip()
    if not phone:
        return _tool_result({"ok": False, "error": "phone required"}, is_error=True)
    built = build_task_prompt(args)
    dial_args = {
        "phone": phone,
        "greeting": built["greeting"],
        "script": built["script"],
        "tools": built["tools"],
        "use_knowledge": built["use_knowledge"],
        "context": (args.get("context") or "outbound"),
        "mode": args.get("mode") or "auto",
    }
    raw = _dial(dial_args)
    text = raw.get("content", [{}])[0].get("text") or "{}"
    try:
        dial_payload = json.loads(text)
    except json.JSONDecodeError:
        dial_payload = {"raw": text}
    return _tool_result({"task": built, "dial": dial_payload, "ok": bool(dial_payload.get("ok"))})


def call_tool(name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    args = arguments or {}

    # aliases → canonical
    aliases = {
        "calls.dial": "telephony.dial",
        "calls.assign_task": "telephony.assign_task",
        "calls.list": "telephony.calls_list",
        "calls.get": "telephony.calls_get",
        "calls.callback": "telephony.callback",
        "calls.list_tools": "telephony.list_tools",
        "line.get": "telephony.inbound_line_get",
        "line.set": "telephony.inbound_line_set",
        "telegram.send": "messenger.telegram_send",
        "telegram.history": "messenger.telegram_history",
        "max.send": "messenger.max_send",
        "max.history": "messenger.max_history",
    }
    name = aliases.get(name, name)

    if name == "office.health":
        targets = {
            "console": console_base(),
            "campaign": campaign_base(),
            "knowledge": knowledge_base(),
            "calendar": calendar_base(),
            "conference": conference_base(),
            "files": files_base(),
            "outreach": outreach_base(),
            "text_bot": text_bot_base(),
            "mailer": mailer_base(),
        }
        services = {k: health_probe(v) for k, v in targets.items()}
        ok = all(bool(v.get("ok")) or v.get("status") == "ok" for v in services.values())
        return _tool_result({"ok": ok, "services": services})

    if name == "office.status":
        return _tool_result(console_request("GET", "/api/status"))

    if name == "telephony.inbound_line_get":
        return _tool_result(console_request("GET", "/api/line"))

    if name == "telephony.inbound_line_set":
        return _tool_result(
            console_request("POST", "/api/line", {"enabled": _as_bool(args.get("enabled"))})
        )

    if name == "telephony.scenario_get":
        ctx = (args.get("context") or "default").strip()
        return _tool_result(console_request("GET", "/api/scenario", query={"context": ctx}))

    if name == "telephony.scenario_set":
        body: dict[str, Any] = {"context": (args.get("context") or "default")}
        for key in ("greeting", "prompt", "tools", "model", "voice", "temperature"):
            if key in args and args[key] is not None:
                body[key] = args[key]
        return _tool_result(console_request("PUT", "/api/scenario", body))

    if name == "telephony.list_tools":
        return _tool_result(console_request("GET", "/api/tools"))

    if name == "telephony.dial":
        return _dial(args)

    if name == "telephony.assign_task":
        return _assign_task(args)

    if name == "telephony.callback":
        phone = (args.get("phone") or "").strip()
        if not phone:
            return _tool_result({"ok": False, "error": "phone required"}, is_error=True)
        body = {"phone": phone}
        for key in ("extension", "line_number", "command_id"):
            if args.get(key):
                body[key] = args[key]
        return _tool_result(console_request("POST", "/api/outbound/callback", body, timeout=45))

    if name == "telephony.calls_list":
        return _tool_result(
            console_request(
                "GET",
                "/api/calls",
                query={
                    "limit": int(args.get("limit") or 20),
                    "context": args.get("context"),
                },
            )
        )

    if name == "telephony.calls_get":
        call_id = (args.get("call_id") or "").strip()
        if not call_id:
            return _tool_result({"ok": False, "error": "call_id required"}, is_error=True)
        return _tool_result(console_request("GET", f"/api/calls/{call_id}"))

    if name == "campaign.status":
        return _tool_result(campaign_request("GET", "/api/campaign/status"))

    if name == "campaign.preview":
        return _tool_result(
            campaign_request(
                "GET",
                "/api/campaign/preview",
                query={"limit": int(args.get("limit") or 30), "sheet": args.get("sheet")},
            )
        )

    if name == "campaign.results":
        return _tool_result(
            campaign_request(
                "GET",
                "/api/campaign/results",
                query={"limit": int(args.get("limit") or 40)},
            )
        )

    if name == "campaign.start":
        body = {"max_calls": int(args.get("max_calls") or 5)}
        if args.get("sheet"):
            body["sheet"] = args["sheet"]
        if "dry_run" in args:
            body["dry_run"] = _as_bool(args.get("dry_run"))
        return _tool_result(campaign_request("POST", "/api/campaign/start", body))

    if name == "campaign.stop":
        return _tool_result(campaign_request("POST", "/api/campaign/stop", {}))

    if name == "campaign.get_script":
        return _tool_result(campaign_request("GET", "/api/campaign/script"))

    if name == "campaign.set_script":
        body = {}
        for key in ("greeting", "script", "tools"):
            if key in args and args[key] is not None:
                body[key] = args[key]
        return _tool_result(campaign_request("PUT", "/api/campaign/script", body))

    if name == "kb.search":
        q = args.get("query") or ""
        limit = int(args.get("limit") or 8)
        max_chars = int(args.get("max_chars") or 6000)
        # Always hit markdown SoT with mode=legacy first (never waits on PG ingest locks).
        legacy = knowledge_request(
            "POST",
            "/api/knowledge/query",
            {
                "topic": q,
                "limit": min(limit, 5),
                "max_chars": max_chars,
                "mode": "legacy",
            },
            timeout=12.0,
        )
        legacy_text = ""
        if isinstance(legacy, dict):
            legacy_text = str(legacy.get("text") or "")
            if not legacy_text and isinstance(legacy.get("legacy"), dict):
                legacy_text = str(legacy["legacy"].get("text") or "")
        # If markdown SoT already answered — return immediately (do not wait on PG locks).
        if legacy.get("ok") or legacy_text:
            return _tool_result(
                {
                    "ok": True,
                    "source": "legacy_first",
                    "query": q,
                    "text": legacy_text or None,
                    "chars": len(legacy_text),
                    "topic": legacy.get("topic") if isinstance(legacy, dict) else None,
                    "topic_id": legacy.get("topic_id") if isinstance(legacy, dict) else None,
                    "legacy": legacy,
                    "knowledge_read_mode": "legacy",
                    "note": "Second Brain skipped when legacy has content (avoids ingest lock timeouts).",
                }
            )
        # Legacy empty — try Second Brain with a short timeout.
        brain = knowledge_request(
            "POST",
            "/api/brain/search",
            {
                "query": q,
                "limit": limit,
                "mode": args.get("mode") or "hybrid",
                "max_chars": max_chars,
            },
            timeout=4.0,
        )
        brain_ok = (
            isinstance(brain, dict)
            and brain.get("ok")
            and brain.get("http_status", 200) < 400
            and not brain.get("error")
            and not brain.get("denied")
            and bool(brain.get("matches") or brain.get("text"))
        )
        if brain_ok:
            brain["source"] = "second_brain"
            return _tool_result(brain)
        return _tool_result(
            {
                "ok": False,
                "error": "kb_search_empty",
                "query": q,
                "legacy": legacy,
                "brain_error": (
                    (brain or {}).get("error")
                    or (brain or {}).get("reason")
                    or (brain or {}).get("denied")
                    or (brain or {}).get("http_status")
                ),
            }
        )

    if name == "kb.get":
        return _tool_result(
            knowledge_request(
                "POST",
                "/api/brain/get",
                {
                    "document_id": args.get("document_id"),
                    "chunk_id": args.get("chunk_id"),
                    "max_chars": int(args.get("max_chars") or 12000),
                },
            )
        )

    if name == "kb.related":
        return _tool_result(
            knowledge_request(
                "POST",
                "/api/brain/graph/expand",
                {
                    "q": args.get("q") or "",
                    "entity_id": args.get("entity_id"),
                    "depth": int(args.get("depth") or 1),
                    "limit": int(args.get("limit") or 40),
                },
            )
        )

    if name == "kb.find_contact":
        return _tool_result(
            knowledge_request(
                "POST",
                "/api/brain/contacts/find",
                {
                    "q": args.get("q") or "",
                    "email": args.get("email") or "",
                    "phone": args.get("phone") or "",
                    "company": args.get("company") or "",
                    "limit": int(args.get("limit") or 20),
                },
            )
        )

    if name == "kb.list_threads":
        return _tool_result(
            knowledge_request(
                "POST",
                "/api/brain/threads/list",
                {
                    "q": args.get("q") or "",
                    "since": args.get("since"),
                    "limit": int(args.get("limit") or 20),
                },
            )
        )

    if name == "kb.ingest_status":
        return _tool_result(knowledge_request("GET", "/api/brain/ingest/status"))

    if name == "kb.health":
        return _tool_result(knowledge_request("GET", "/api/brain/health"))

    if name == "knowledge.query":
        q = (args.get("query") or args.get("topic") or "").strip()
        # Default legacy — Grok must not hang when Second Brain PG is locked by ingest.
        mode = (args.get("mode") or "legacy").strip().lower() or "legacy"
        body = {
            "topic": q,
            "limit": int(args.get("limit") or 5),
            "max_chars": int(args.get("max_chars") or 4000),
            "mode": mode,
        }
        return _tool_result(
            knowledge_request("POST", "/api/knowledge/query", body, timeout=15.0)
        )

    if name == "knowledge.topics":
        return _tool_result(knowledge_request("GET", "/api/knowledge/topics"))

    if name == "knowledge.get":
        return _tool_result(
            knowledge_request("POST", "/api/knowledge/get", {"id": args.get("id")})
        )

    if name == "calendar.check":
        body = {"start": args.get("start")}
        if args.get("timezone"):
            body["timezone"] = args["timezone"]
        return _tool_result(calendar_request("POST", "/api/calendar/check", body))

    if name == "calendar.suggest":
        body = {"start": args.get("start")}
        for key in ("timezone", "duration_min", "suggestions_count", "search_hours_ahead"):
            if args.get(key) is not None:
                body[key] = args[key]
        return _tool_result(calendar_request("POST", "/api/calendar/suggest", body))

    if name == "calendar.create":
        body = {"start": args.get("start"), "summary": args.get("summary")}
        for key in (
            "end",
            "description",
            "attendee_email",
            "timezone",
            "create_telemost",
            "send_telemost_invite",
            "location",
        ):
            if args.get(key) is not None:
                body[key] = args[key]
        return _tool_result(calendar_request("POST", "/api/calendar/create", body))

    if name == "conference.create":
        body = {}
        for key in (
            "title",
            "invitees",
            "message",
            "when_text",
            "waiting_room_level",
            "send_invites",
        ):
            if key in args and args[key] is not None:
                body[key] = args[key]
        return _tool_result(conference_request("POST", "/api/conferences", body))

    if name == "messenger.status":
        return _tool_result(text_bot_request("GET", "/api/messenger/status"))

    if name == "messenger.chats":
        return _tool_result(
            text_bot_request(
                "GET",
                "/api/messenger/chats",
                query={
                    "channel": args.get("channel"),
                    "limit": int(args.get("limit") or 50),
                },
            )
        )

    if name in {
        "messenger.history",
        "messenger.telegram_history",
        "messenger.max_history",
    }:
        channel = args.get("channel")
        if name == "messenger.telegram_history":
            channel = channel or "telegram"
        if name == "messenger.max_history":
            channel = channel or "max"
        return _tool_result(
            text_bot_request(
                "GET",
                "/api/messenger/history",
                query={
                    "session_id": args.get("session_id"),
                    "channel": channel,
                    "user_id": args.get("user_id"),
                    "chat_id": args.get("chat_id"),
                    "limit": int(args.get("limit") or 40),
                    "include_tools": (
                        "true" if args.get("include_tools") else "false"
                    ),
                },
            )
        )

    if name == "messenger.messages":
        return _tool_result(
            text_bot_request(
                "GET",
                "/api/messenger/messages",
                query={
                    "channel": args.get("channel") or "max",
                    "chat_id": args.get("chat_id"),
                    "message_ids": args.get("message_ids"),
                    "count": int(args.get("count") or 50),
                    "from_ts": args.get("from_ts"),
                    "to_ts": args.get("to_ts"),
                },
            )
        )

    if name == "messenger.send":
        body = {
            "channel": args.get("channel"),
            "text": args.get("text"),
            "chat_id": args.get("chat_id"),
            "user_id": args.get("user_id"),
            "business_connection_id": args.get("business_connection_id"),
            "record_history": args.get("record_history", True),
        }
        return _tool_result(text_bot_request("POST", "/api/messenger/send", body))

    if name == "messenger.telegram_send":
        body = {
            "channel": "telegram",
            "text": args.get("text"),
            "chat_id": args.get("chat_id"),
            "user_id": args.get("user_id"),
        }
        return _tool_result(text_bot_request("POST", "/api/messenger/send", body))

    if name == "messenger.max_send":
        body = {
            "channel": "max",
            "text": args.get("text"),
            "chat_id": args.get("chat_id"),
            "user_id": args.get("user_id"),
        }
        return _tool_result(text_bot_request("POST", "/api/messenger/send", body))

    if name == "messenger.chat":
        return _tool_result(
            text_bot_request(
                "POST",
                "/api/chat",
                {
                    "user_id": args.get("user_id"),
                    "text": args.get("text"),
                    "channel": args.get("channel") or "api",
                },
            )
        )

    if name == "messenger.chat_reset":
        return _tool_result(
            text_bot_request(
                "POST",
                "/api/chat/reset",
                {
                    "user_id": args.get("user_id"),
                    "channel": args.get("channel") or "api",
                },
            )
        )

    if name == "outreach.dashboard":
        return _tool_result(outreach_request("GET", "/api/dashboard"))

    if name == "outreach.status":
        return _tool_result(outreach_request("GET", "/status"))

    if name == "outreach.outbox":
        return _tool_result(
            outreach_request(
                "GET",
                "/api/outbox",
                query={
                    "limit": int(args.get("limit") or 30),
                    "offset": int(args.get("offset") or 0),
                    "status": args.get("status"),
                    "q": args.get("q"),
                },
            )
        )

    if name == "outreach.outbox_set_status":
        row_id = int(args.get("row_id"))
        return _tool_result(
            outreach_request(
                "PATCH",
                f"/api/outbox/{row_id}",
                {"status": args.get("status")},
            )
        )

    if name == "outreach.replies":
        return _tool_result(
            outreach_request(
                "GET",
                "/api/replies",
                query={
                    "limit": int(args.get("limit") or 50),
                    "offset": int(args.get("offset") or 0),
                    "full": 1 if _as_bool(args.get("full"), True) else 0,
                },
            )
        )

    if name == "outreach.replies_backfill":
        return _tool_result(
            outreach_request(
                "POST",
                "/api/replies/backfill",
                query={"limit": int(args.get("limit") or 250)},
                timeout=180.0,
            )
        )

    if name == "outreach.settings_get":
        return _tool_result(outreach_request("GET", "/api/settings"))

    if name == "outreach.settings_set":
        settings = args.get("settings")
        if not isinstance(settings, dict):
            return _tool_result({"ok": False, "error": "settings object required"}, is_error=True)
        return _tool_result(outreach_request("PUT", "/api/settings", settings))

    if name == "outreach.packs":
        return _tool_result(outreach_request("GET", "/api/packs"))

    if name == "outreach.pack_get":
        pack_id = (args.get("pack_id") or "").strip()
        return _tool_result(outreach_request("GET", f"/api/packs/{pack_id}"))

    if name == "outreach.pack_apply":
        body: dict[str, Any] = {"pack_id": args.get("pack_id")}
        if args.get("step") is not None:
            body["step"] = args["step"]
        return _tool_result(outreach_request("POST", "/api/packs/apply", body))

    if name == "outreach.preview":
        body = {}
        for key in ("email", "contact_name", "company"):
            if args.get(key) is not None:
                body[key] = args[key]
        return _tool_result(outreach_request("POST", "/api/preview", body))

    if name == "outreach.send_one":
        body = {"to": args.get("to")}
        for key in ("contact_name", "dry_run", "create_bitrix_deal", "attach_presentation"):
            if key in args and args[key] is not None:
                body[key] = args[key]
        return _tool_result(outreach_request("POST", "/send-one", body))

    if name == "outreach.send_batch":
        body = {
            "limit": int(args.get("limit") or 1),
            "dry_run": _as_bool(args.get("dry_run"), False),
        }
        if args.get("only_email"):
            body["only_email"] = args["only_email"]
        return _tool_result(outreach_request("POST", "/send-batch", body))

    if name == "outreach.sync":
        return _tool_result(outreach_request("POST", "/sync", {}))

    if name == "outreach.check_replies":
        return _tool_result(outreach_request("POST", "/check-replies", {}))

    if name == "outreach.rebuild_outbox":
        return _tool_result(
            outreach_request("POST", "/api/modules/clients/rebuild-outbox", {})
        )

    if name in {"files.status", "mailru.status"}:
        return _tool_result(health_probe(files_base()))

    if name in {"files.list", "mailru.list"}:
        source = "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru")
        return _tool_result(
            files_request(
                "POST",
                "/api/files/list",
                {"source": source, "path": args.get("path") or "/"},
            )
        )

    if name in {"files.search", "mailru.search"}:
        source = "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru")
        return _tool_result(
            files_request(
                "POST",
                "/api/files/search",
                {
                    "query": args.get("query"),
                    "source": source,
                    "path": args.get("path") or "/",
                    "limit": int(args.get("limit") or 40),
                },
            )
        )

    if name in {"files.fetch", "mailru.fetch"}:
        body = {
            "source": "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru"),
            "path": args.get("path"),
        }
        for key in ("ref", "repo"):
            if args.get(key):
                body[key] = args[key]
        return _tool_result(files_request("POST", "/api/files/fetch", body))

    if name in {"files.read", "mailru.read"}:
        body = {
            "source": "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru"),
            "path": args.get("path"),
            "max_chars": int(args.get("max_chars") or 50000),
        }
        for key in ("ref", "repo"):
            if args.get(key):
                body[key] = args[key]
        return _tool_result(files_request("POST", "/api/files/read", body))

    if name in {"files.send", "mailru.send"}:
        path = (args.get("path") or "").strip()
        body_text = args.get("body") or args.get("text")
        via = args.get("via")
        # Treat "/", "." or path without filename extension as "no file"
        path_name = path.rstrip("/").split("/")[-1] if path else ""
        looks_like_file = bool(path_name) and ("." in path_name) and path not in {"/", ".", "./"}
        text_mode = bool(body_text) and via not in ("telegram", "tg") and (
            not looks_like_file or name == "mailru.send" and not looks_like_file
        )
        # mailru.send + body → always text SMTP unless a real cloud file path is given
        if name == "mailru.send" and body_text and via not in ("telegram", "tg") and not looks_like_file:
            text_mode = True
        if text_mode:
            mail_body = {
                "to": args.get("to"),
                "subject": args.get("subject") or "Сообщение Quantum Labs",
                "body": body_text,
                "mailbox": (args.get("mailbox") or args.get("from") or "office"),
            }
            for key in ("html", "cc", "reply_to"):
                if args.get(key) is not None:
                    mail_body[key] = args[key]
            return _tool_result(outreach_request("POST", "/api/mail/send", mail_body))
        if not looks_like_file:
            return _tool_result(
                {
                    "ok": False,
                    "error": "path_or_body_required",
                    "message": (
                        "Текстовое письмо: to + subject + body (без path). "
                        "Файл с Облака: path=/Папка/file.pdf + via + to. "
                        "Или используйте mail.send."
                    ),
                    "schema_hint": {
                        "text_email": {"to": "...", "subject": "...", "body": "..."},
                        "cloud_file": {"path": "/file.pdf", "via": "email", "to": "..."},
                        "preferred_text_tool": "mail.send",
                    },
                },
                is_error=True,
            )
        body = {
            "source": "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru"),
            "path": path,
            "via": via or "email",
            "to": args.get("to"),
        }
        for key in ("caption", "subject", "ref", "repo"):
            if args.get(key) is not None:
                body[key] = args[key]
        if body_text and not body.get("caption"):
            body["caption"] = body_text
        return _tool_result(files_request("POST", "/api/files/send", body))

    if name in {"files.upload", "mailru.upload"}:
        body = {
            "source": "mailru" if name.startswith("mailru.") else (args.get("source") or "mailru"),
            "path": args.get("path"),
            "overwrite": _as_bool(args.get("overwrite"), True),
            "ensure_parents": _as_bool(args.get("ensure_parents"), True),
        }
        if args.get("text") is not None:
            body["text"] = args["text"]
        if args.get("content_base64") is not None:
            body["content_base64"] = args["content_base64"]
        if args.get("content_type") is not None:
            body["content_type"] = args["content_type"]
        return _tool_result(files_request("POST", "/api/files/upload", body, timeout=180.0))

    if name == "mail.send":
        body = {
            "to": args.get("to"),
            "subject": args.get("subject"),
        }
        for key in ("cc", "body", "html", "reply_to"):
            if args.get(key) is not None:
                body[key] = args[key]
        mailbox = (args.get("mailbox") or args.get("from") or "office").strip()
        body["mailbox"] = mailbox
        return _tool_result(outreach_request("POST", "/api/mail/send", body))

    if name == "outreach.leads_import":
        body = {
            "csv": args.get("csv") or "",
            "queue": _as_bool(args.get("queue"), True),
            "apply_pack": _as_bool(args.get("apply_pack"), False),
            "skip_duplicates": _as_bool(args.get("skip_duplicates"), True),
        }
        if args.get("pack_id"):
            body["pack_id"] = args["pack_id"]
        return _tool_result(outreach_request("POST", "/api/leads/import", body, timeout=120.0))

    if name == "outreach.lead_check":
        body = {}
        for key in ("email", "company"):
            if args.get(key):
                body[key] = args[key]
        return _tool_result(outreach_request("POST", "/api/leads/check", body))

    return _tool_result(f"unknown tool: {name}", is_error=True)
