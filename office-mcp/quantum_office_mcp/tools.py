"""MCP tool catalog for Quantum Office."""

from __future__ import annotations

from typing import Any

TOOLS: list[dict[str, Any]] = [
    # ---- office ----
    {
        "name": "office.health",
        "description": "Probe /health for all office services.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "office.status",
        "description": "Quantum Console full status (Asterisk, units, line, outbound).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ---- telephony inbound ----
    {
        "name": "telephony.inbound_line_get",
        "description": "Get inbound auto-line state (AstDB). When off — Busy, no AI.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "telephony.inbound_line_set",
        "description": "Enable/disable inbound auto-line.",
        "inputSchema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    },
    {
        "name": "telephony.scenario_get",
        "description": "Get AVA scenario for inbound (default) or outbound profile.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "enum": ["default", "outbound"],
                    "default": "default",
                }
            },
        },
    },
    {
        "name": "telephony.scenario_set",
        "description": (
            "Update greeting/prompt/tools for ONE profile only "
            "(default=inbound, outbound=outbound). Isolated."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "context": {
                    "type": "string",
                    "enum": ["default", "outbound"],
                    "default": "default",
                },
                "greeting": {"type": "string"},
                "prompt": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "model": {"type": "string"},
                "voice": {"type": "string"},
                "temperature": {"type": "number"},
            },
        },
    },
    {
        "name": "telephony.list_tools",
        "description": "Catalog of in-call AVA tools.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ---- telephony outbound ----
    {
        "name": "telephony.dial",
        "description": "Originate one outbound AVA call with optional per-call script.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "use_knowledge": {"type": "boolean", "default": False},
                "context": {"type": "string", "default": "outbound"},
                "provider": {"type": "string"},
                "caller_id_num": {"type": "string"},
                "caller_id_name": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "telephony.assign_task",
        "description": (
            "Sales/LPR task → build playbook → dial. Prefer for Grok/management bots."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "company": {"type": "string"},
                "contact_name": {"type": "string"},
                "goal": {"type": "string"},
                "product": {"type": "string"},
                "notes": {"type": "string"},
                "find_lpr": {"type": "boolean", "default": True},
                "book_meeting": {"type": "boolean", "default": True},
                "language": {"type": "string", "default": "ru"},
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "use_knowledge": {"type": "boolean", "default": True},
                "context": {"type": "string", "default": "outbound"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "telephony.callback",
        "description": "Outbound via Mango VPBX callback (extension → PSTN).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "extension": {"type": "string"},
                "line_number": {"type": "string"},
                "command_id": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "telephony.calls_list",
        "description": "List recent calls (inbound+outbound). Filter by context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 20},
                "context": {
                    "type": "string",
                    "description": "default | outbound | omit for all",
                },
            },
        },
    },
    {
        "name": "telephony.calls_get",
        "description": "Full transcript + tools for one call_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
    # aliases kept for earlier MCP clients
    {
        "name": "calls.dial",
        "description": "Alias of telephony.dial.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "use_knowledge": {"type": "boolean"},
                "context": {"type": "string"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "calls.assign_task",
        "description": "Alias of telephony.assign_task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {"type": "string"},
                "company": {"type": "string"},
                "contact_name": {"type": "string"},
                "goal": {"type": "string"},
                "product": {"type": "string"},
                "notes": {"type": "string"},
                "find_lpr": {"type": "boolean"},
                "book_meeting": {"type": "boolean"},
                "language": {"type": "string"},
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
                "use_knowledge": {"type": "boolean"},
            },
            "required": ["phone"],
        },
    },
    {
        "name": "calls.list",
        "description": "Alias of telephony.calls_list.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer"},
                "context": {"type": "string"},
            },
        },
    },
    {
        "name": "calls.get",
        "description": "Alias of telephony.calls_get.",
        "inputSchema": {
            "type": "object",
            "properties": {"call_id": {"type": "string"}},
            "required": ["call_id"],
        },
    },
    {
        "name": "line.get",
        "description": "Alias of telephony.inbound_line_get.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "line.set",
        "description": "Alias of telephony.inbound_line_set.",
        "inputSchema": {
            "type": "object",
            "properties": {"enabled": {"type": "boolean"}},
            "required": ["enabled"],
        },
    },
    # ---- campaign ----
    {
        "name": "campaign.status",
        "description": "Sheets-campaign worker status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.preview",
        "description": "Preview sheet leads without marks.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 30},
                "sheet": {"type": "string"},
            },
        },
    },
    {
        "name": "campaign.results",
        "description": "Local campaign dial results.",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 40}},
        },
    },
    {
        "name": "campaign.start",
        "description": "Start Sheets campaign worker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "max_calls": {"type": "integer", "default": 5},
                "sheet": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
        },
    },
    {
        "name": "campaign.stop",
        "description": "Stop Sheets campaign worker.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.get_script",
        "description": "Get Sheets-campaign greeting + playbook.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "campaign.set_script",
        "description": "Update Sheets-campaign greeting/script/tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "greeting": {"type": "string"},
                "script": {"type": "string"},
                "tools": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    # ---- second brain / knowledge ----
    {
        "name": "kb.search",
        "description": (
            "Knowledge search: markdown SoT first (always), then Second Brain if fast. "
            "Does not hang when Postgres ingest locks brain search."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 8},
                "mode": {
                    "type": "string",
                    "enum": ["hybrid", "keyword", "semantic"],
                    "default": "hybrid",
                },
                "max_chars": {"type": "integer", "default": 6000},
            },
            "required": ["query"],
        },
    },
    {
        "name": "kb.get",
        "description": "Fetch one Second Brain document/chunk by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "document_id": {"type": "string"},
                "chunk_id": {"type": "string"},
                "max_chars": {"type": "integer", "default": 12000},
            },
        },
    },
    {
        "name": "kb.related",
        "description": "Expand knowledge graph around person/company/topic.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "entity_id": {"type": "string"},
                "depth": {"type": "integer", "default": 1},
                "limit": {"type": "integer", "default": 40},
            },
        },
    },
    {
        "name": "kb.find_contact",
        "description": "Find office contacts by name/email/phone/company (Second Brain).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "company": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "kb.list_threads",
        "description": "List email threads from Second Brain.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "since": {"type": "string"},
                "limit": {"type": "integer", "default": 20},
            },
        },
    },
    {
        "name": "kb.ingest_status",
        "description": "Second Brain ingest markers + corpus stats.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "kb.health",
        "description": "Second Brain /api/brain/health.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "knowledge.query",
        "description": (
            "Knowledge query. Default mode=legacy (fast markdown). "
            "Pass mode=brain only if you need Second Brain."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
                "max_chars": {"type": "integer", "default": 4000},
                "mode": {
                    "type": "string",
                    "enum": ["legacy", "brain", "dual_compare"],
                    "default": "legacy",
                },
            },
        },
    },
    {
        "name": "knowledge.topics",
        "description": "List legacy knowledge topics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "knowledge.get",
        "description": (
            "Get legacy knowledge by section id OR catalog topic id "
            "(e.g. audience, faq, payouts)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "string"}},
            "required": ["id"],
        },
    },
    # ---- calendar / conference ----
    {
        "name": "calendar.check",
        "description": "Check if a calendar slot is free.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "timezone": {"type": "string"},
            },
            "required": ["start"],
        },
    },
    {
        "name": "calendar.suggest",
        "description": "Suggest free calendar slots.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "timezone": {"type": "string"},
                "duration_min": {"type": "integer"},
                "suggestions_count": {"type": "integer"},
                "search_hours_ahead": {"type": "integer"},
            },
            "required": ["start"],
        },
    },
    {
        "name": "calendar.create",
        "description": "Create calendar event (optional Telemost).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "start": {"type": "string"},
                "end": {"type": "string"},
                "summary": {"type": "string"},
                "description": {"type": "string"},
                "attendee_email": {"type": "string"},
                "timezone": {"type": "string"},
                "create_telemost": {"type": "boolean"},
                "send_telemost_invite": {"type": "boolean"},
                "location": {"type": "string"},
            },
            "required": ["start", "summary"],
        },
    },
    {
        "name": "conference.create",
        "description": "Create Yandex Telemost conference + optional email invites.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "invitees": {"type": "array", "items": {"type": "string"}},
                "message": {"type": "string"},
                "when_text": {"type": "string"},
                "waiting_room_level": {"type": "string"},
                "send_invites": {"type": "boolean", "default": True},
            },
        },
    },
    # ---- messengers: telegram / max ----
    {
        "name": "messenger.status",
        "description": "Telegram + Max messenger configuration status (text-bot).",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "messenger.chats",
        "description": (
            "List recent Telegram/Max/API dialogue sessions "
            "(session_id like telegram:123 or max:456)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Filter: telegram|max|telegram_business|api|…",
                },
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    {
        "name": "messenger.history",
        "description": (
            "Read conversation history for a session (local secretary DB). "
            "Pass session_id OR channel+user_id/chat_id. "
            "For Telegram this is what the bot saw/sent — not full TG cloud history. "
            "For company knowledge use kb.search / knowledge.query."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "e.g. telegram:963782 or max:12239171",
                },
                "channel": {"type": "string"},
                "user_id": {"type": "string"},
                "chat_id": {"type": "string"},
                "limit": {"type": "integer", "default": 40},
                "include_tools": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "messenger.messages",
        "description": (
            "Native Max chat messages via Max API GET /messages "
            "(bot must be chat admin with read_all_messages). "
            "For Telegram use messenger.history."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["max"],
                    "default": "max",
                },
                "chat_id": {"type": "string"},
                "message_ids": {"type": "string"},
                "count": {"type": "integer", "default": 50},
                "from_ts": {"type": "integer"},
                "to_ts": {"type": "integer"},
            },
        },
    },
    {
        "name": "messenger.send",
        "description": "Send outbound message via Telegram or Max.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "enum": ["telegram", "max", "tg", "telegram_business"],
                },
                "text": {"type": "string"},
                "chat_id": {"type": "string"},
                "user_id": {"type": "string"},
                "business_connection_id": {"type": "string"},
                "record_history": {
                    "type": "boolean",
                    "default": True,
                    "description": "Save outbound text into session history",
                },
            },
            "required": ["channel", "text"],
        },
    },
    {
        "name": "messenger.chat",
        "description": (
            "Talk to the AI secretary over HTTP (uses Second Brain / company knowledge). "
            "Any channel id; for raw send without secretary use messenger.send."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "text": {"type": "string"},
                "channel": {"type": "string", "default": "api"},
            },
            "required": ["user_id", "text"],
        },
    },
    {
        "name": "messenger.chat_reset",
        "description": "Reset secretary dialogue session.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "channel": {"type": "string", "default": "api"},
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "telegram.send",
        "description": "Alias: send Telegram message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "text": {"type": "string"},
                "user_id": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "telegram.history",
        "description": "Alias: messenger.history with channel=telegram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "chat_id": {"type": "string"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "default": 40},
            },
        },
    },
    {
        "name": "max.send",
        "description": "Alias: send Max messenger message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "chat_id": {"type": "string"},
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "max.history",
        "description": (
            "Alias: session history for Max (messenger.history channel=max). "
            "For native Max API messages use messenger.messages."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "chat_id": {"type": "string"},
                "session_id": {"type": "string"},
                "limit": {"type": "integer", "default": 40},
            },
        },
    },
    # ---- outreach ----
    {
        "name": "outreach.dashboard",
        "description": "Email outreach dashboard metrics.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.status",
        "description": "Lightweight outreach /status.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.outbox",
        "description": "List outreach outbox rows.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 30},
                "offset": {"type": "integer", "default": 0},
                "status": {"type": "string"},
                "q": {"type": "string"},
            },
        },
    },
    {
        "name": "outreach.outbox_set_status",
        "description": "Patch outbox row status (pending|skipped|failed|sent|replied).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "row_id": {"type": "integer"},
                "status": {"type": "string"},
            },
            "required": ["row_id", "status"],
        },
    },
    {
        "name": "outreach.replies",
        "description": "List inbound email replies with full body text (for drafting answers).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
                "full": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include full body_text (default true)",
                },
            },
        },
    },
    {
        "name": "outreach.replies_backfill",
        "description": (
            "Re-scan IMAP and fill empty body_text on inbound replies "
            "(fixes older rows stored without text)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": 250,
                    "description": "How many recent IMAP messages to scan",
                },
            },
        },
    },
    {
        "name": "outreach.settings_get",
        "description": "Get outreach settings snapshot.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.settings_set",
        "description": "Update outreach settings (partial dict).",
        "inputSchema": {
            "type": "object",
            "properties": {"settings": {"type": "object"}},
            "required": ["settings"],
        },
    },
    {
        "name": "outreach.packs",
        "description": (
            "List industry email packs (id, subject, plain_preview). "
            "For FULL letter plain/html/steps call outreach.pack_get."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.pack_get",
        "description": "Get one pack by id with full letter plain/html for all steps.",
        "inputSchema": {
            "type": "object",
            "properties": {"pack_id": {"type": "string"}},
            "required": ["pack_id"],
        },
    },
    {
        "name": "outreach.pack_apply",
        "description": "Apply industry pack to campaign templates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pack_id": {"type": "string"},
                "step": {"type": "integer"},
            },
            "required": ["pack_id"],
        },
    },
    {
        "name": "outreach.preview",
        "description": "Preview outreach email render.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "contact_name": {"type": "string"},
                "company": {"type": "string"},
            },
        },
    },
    {
        "name": "outreach.send_one",
        "description": "Send one test/marketing email to an address.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "contact_name": {"type": "string"},
                "dry_run": {"type": "boolean", "default": False},
                "create_bitrix_deal": {"type": "boolean", "default": False},
                "attach_presentation": {"type": "boolean"},
            },
            "required": ["to"],
        },
    },
    {
        "name": "outreach.send_batch",
        "description": "Send batch from outbox (or dry_run).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 1},
                "dry_run": {"type": "boolean", "default": False},
                "only_email": {"type": "string"},
            },
        },
    },
    {
        "name": "outreach.sync",
        "description": "Sync Bitrix clients into outreach store.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.check_replies",
        "description": "Poll mailbox for replies and update outbox.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "outreach.rebuild_outbox",
        "description": "Rebuild outbox from synced clients.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    # ---- files / Mail.ru Cloud ----
    {
        "name": "files.status",
        "description": (
            "File broker health: Mail.ru Cloud / Yadisk / local configured flags."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "files.list",
        "description": (
            "Browse cloud/local directory. Default source=mailru (Mail.ru Облако WebDAV)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "default": "mailru",
                    "description": "mailru | yadisk | local",
                },
                "path": {"type": "string", "default": "/"},
            },
        },
    },
    {
        "name": "files.search",
        "description": "Search files by name under path (default Mail.ru Cloud).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "source": {"type": "string", "default": "mailru"},
                "path": {"type": "string", "default": "/"},
                "limit": {"type": "integer", "default": 40},
            },
            "required": ["query"],
        },
    },
    {
        "name": "files.fetch",
        "description": "Fetch file metadata only (size/name, not content).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "default": "mailru"},
                "path": {"type": "string"},
                "ref": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "files.read",
        "description": (
            "Read TEXT content of a cloud file for agents (UTF-8/cp1251). "
            "Default source=mailru. For PDF/Office use files.send."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "source": {"type": "string", "default": "mailru"},
                "max_chars": {"type": "integer", "default": 50000},
                "ref": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "files.send",
        "description": "Fetch file from cloud/local and send via email or Telegram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {"type": "string", "default": "mailru"},
                "path": {"type": "string"},
                "via": {"type": "string", "enum": ["email", "telegram", "mail", "tg"]},
                "to": {"type": "string"},
                "caption": {"type": "string"},
                "subject": {"type": "string"},
                "ref": {"type": "string"},
                "repo": {"type": "string"},
            },
            "required": ["path", "via", "to"],
        },
    },
    {
        "name": "files.upload",
        "description": (
            "Save a file TO Mail.ru Облако (company cloud disk). "
            "Use text= for UTF-8 notes or content_base64= for binary (PDF/Office). "
            "Path must include filename, e.g. /MCP/notes/memo.txt"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "text": {"type": "string"},
                "content_base64": {"type": "string"},
                "content_type": {"type": "string"},
                "source": {"type": "string", "default": "mailru"},
                "overwrite": {"type": "boolean", "default": True},
                "ensure_parents": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mailru.status",
        "description": "Mail.ru Cloud WebDAV status via ava-files /health.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "mailru.list",
        "description": "List directory in Mail.ru Облако (company docs).",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string", "default": "/"}},
        },
    },
    {
        "name": "mailru.search",
        "description": "Search Mail.ru Облако by filename substring.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string", "default": "/"},
                "limit": {"type": "integer", "default": 40},
            },
            "required": ["query"],
        },
    },
    {
        "name": "mailru.read",
        "description": "Read text file from Mail.ru Облако (company data for MCP/Grok).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "default": 50000},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mailru.fetch",
        "description": "Metadata for a Mail.ru Cloud path.",
        "inputSchema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "mailru.send",
        "description": (
            "EMAIL / Telegram. TEXT LETTER (preferred for plain mail): "
            "arguments {to, subject, body} — path MUST be omitted; sends via office@ SMTP. "
            "CLOUD FILE: {path:'/file.pdf', via:'email'|'telegram', to}. "
            "Also see mail.send for text-only. Schema revision includes body; path is NOT required."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email or Telegram chat id"},
                "subject": {
                    "type": "string",
                    "description": "Email subject (use with body for text letter)",
                },
                "body": {
                    "type": "string",
                    "description": "Plain text letter body. If set and path omitted → SMTP text email.",
                },
                "html": {"type": "string", "description": "Optional HTML body for text letter"},
                "path": {
                    "type": "string",
                    "description": "OPTIONAL. Cloud file path WITH extension (e.g. /doc.pdf). Omit for text letter.",
                },
                "via": {
                    "type": "string",
                    "enum": ["email", "telegram", "mail", "tg"],
                    "default": "email",
                },
                "caption": {"type": "string"},
                "mailbox": {
                    "type": "string",
                    "description": "office | cold for text mode",
                    "default": "office",
                },
            },
            "required": ["to"],
        },
    },
    {
        "name": "mailru.upload",
        "description": (
            "Alias of files.upload — save text/base64 file to Mail.ru Облако "
            "(company cloud disk)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "text": {"type": "string"},
                "content_base64": {"type": "string"},
                "content_type": {"type": "string"},
                "overwrite": {"type": "boolean", "default": True},
                "ensure_parents": {"type": "boolean", "default": True},
            },
            "required": ["path"],
        },
    },
    {
        "name": "mail.send",
        "description": (
            "PRIMARY tool for plain text/html email (not a cloud file). "
            "mailbox=office → office@quantumlabs.ru; mailbox=cold when OUTREACH_COLD_* configured. "
            "Alias: mailru.send with to+subject+body and no path."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "cc": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string", "description": "Plain text body"},
                "html": {"type": "string"},
                "reply_to": {"type": "string"},
                "from": {
                    "type": "string",
                    "description": "Mailbox key: office | cold | full email if allowed",
                },
                "mailbox": {
                    "type": "string",
                    "description": "Alias of from: office | cold",
                },
            },
            "required": ["to", "subject"],
        },
    },
    {
        "name": "outreach.leads_import",
        "description": (
            "Import leads CSV into outreach outbox. Columns: company, segment, website, "
            "email, phone, contact_name (LPR), source. Dedups against Bitrix clients + outbox. "
            "Segments map to packs: agents_fintech, agents_1c, agents_accounting, construction, "
            "blogger_agencies, agri, rental (+ lombards/mfo/…)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "csv": {"type": "string", "description": "CSV text (header row required)"},
                "pack_id": {
                    "type": "string",
                    "description": "Optional pack/segment to apply after import",
                },
                "queue": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enqueue as pending outbox rows",
                },
                "apply_pack": {
                    "type": "boolean",
                    "default": False,
                    "description": "Also apply pack templates to campaign settings",
                },
                "skip_duplicates": {
                    "type": "boolean",
                    "default": True,
                },
            },
            "required": ["csv"],
        },
    },
    {
        "name": "outreach.lead_check",
        "description": "Check email/company against Bitrix clients mirror and outreach history (dedup).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {"type": "string"},
                "company": {"type": "string"},
            },
        },
    },
]
