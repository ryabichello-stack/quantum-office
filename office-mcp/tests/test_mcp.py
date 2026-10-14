"""Unit tests for Quantum Office MCP (no live services required)."""

from __future__ import annotations

import json

from quantum_office_mcp.script_builder import build_task_prompt
from quantum_office_mcp.server import TOOLS, _handle, call_tool


def test_tools_registered():
    names = {t["name"] for t in TOOLS}
    assert "telephony.assign_task" in names or "calls.assign_task" in names
    assert "telephony.dial" in names or "calls.dial" in names
    assert "campaign.start" in names
    assert "office.health" in names
    assert "kb.search" in names
    assert "kb.find_contact" in names
    assert "calendar.suggest" in names
    assert "outreach.dashboard" in names
    assert "messenger.send" in names
    assert "mailru.read" in names
    assert "mail.send" in names
    assert "files.read" in names
    assert "files.upload" in names
    assert "mailru.upload" in names
    assert "files.send" in names
    assert "calendar.create" in names
    assert "conference.create" in names


def test_mailru_send_text_routes_to_mail_send(monkeypatch):
    captured: dict = {}

    def fake_outreach(method, path, body=None, query=None, timeout=60.0):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {"ok": True, "message_id": "mid-1", "from": "office@quantumlabs.ru"}

    monkeypatch.setattr("quantum_office_mcp.handlers.outreach_request", fake_outreach)
    out = call_tool(
        "mailru.send",
        {
            "to": "a@example.com",
            "subject": "Hi",
            "body": "Plain text letter",
        },
    )
    assert out.get("isError") is not True
    assert captured["path"] == "/api/mail/send"
    assert captured["body"]["body"] == "Plain text letter"
    assert captured["body"]["mailbox"] == "office"


def test_initialize_and_list_tools():
    init = _handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init["result"]["serverInfo"]["name"] == "quantum-office"
    listed = _handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert len(listed["result"]["tools"]) >= 40


def test_unknown_tool():
    out = call_tool("no.such.tool", {})
    assert out.get("isError") is True


def test_dial_requires_phone():
    out = call_tool("telephony.dial", {})
    assert out.get("isError") is True
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is False


def test_build_task_prompt_ru():
    built = build_task_prompt(
        {
            "company": "ТестБанк",
            "contact_name": "Пётр",
            "goal": "найти ЛПР",
            "find_lpr": True,
            "book_meeting": True,
        }
    )
    assert "Пётр" in built["greeting"]
    assert "ЛПР" in built["script"] or "лиц" in built["script"].lower()
    assert "get_company_knowledge" in built["tools"]
    assert built["use_knowledge"] is True


def test_assign_task_calls_dial(monkeypatch):
    captured: dict = {}

    def fake_console(method, path, body=None, query=None, timeout=60.0):
        captured["method"] = method
        captured["path"] = path
        captured["body"] = body
        return {
            "ok": True,
            "mode": "sip_ari",
            "channel_id": "ch-1",
            "phone": body["phone"],
            "note": "test",
        }

    monkeypatch.setattr("quantum_office_mcp.handlers.console_request", fake_console)
    out = call_tool(
        "calls.assign_task",
        {
            "phone": "+79001112233",
            "company": "ООО Ромашка",
            "goal": "записать на демо",
        },
    )
    payload = json.loads(out["content"][0]["text"])
    assert captured["path"] == "/api/outbound/dial"
    assert captured["body"]["phone"] == "+79001112233"
    assert captured["body"]["mode"] == "auto"
    assert captured["body"]["script"]
    assert payload["dial"]["dial"]["channel_id"] == "ch-1"
    assert payload["ok"] is True


def test_campaign_start(monkeypatch):
    def fake_campaign(method, path, body=None, query=None, timeout=60.0):
        assert method == "POST"
        assert path == "/api/campaign/start"
        assert body["max_calls"] == 3
        return {"ok": True, "running": True}

    monkeypatch.setattr("quantum_office_mcp.handlers.campaign_request", fake_campaign)
    out = call_tool("campaign.start", {"max_calls": 3})
    payload = json.loads(out["content"][0]["text"])
    assert payload["running"] is True


def test_office_health(monkeypatch):
    def fake_health(url, timeout=5.0):
        return {"ok": True, "service": url}

    monkeypatch.setattr("quantum_office_mcp.handlers.health_probe", fake_health)
    out = call_tool("office.health", {})
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is True
    assert "console" in payload["services"]


def test_mailru_read(monkeypatch):
    captured: dict = {}

    def fake_files(method, path, body=None, timeout=60.0):
        captured["path"] = path
        captured["body"] = body
        return {"ok": True, "text": "данные компании", "source": "mailru"}

    monkeypatch.setattr("quantum_office_mcp.handlers.files_request", fake_files)
    out = call_tool("mailru.read", {"path": "/Клиенты/readme.txt"})
    payload = json.loads(out["content"][0]["text"])
    assert captured["path"] == "/api/files/read"
    assert captured["body"]["source"] == "mailru"
    assert payload["text"] == "данные компании"


def test_messenger_send(monkeypatch):
    def fake_tb(method, path, body=None, query=None, timeout=90.0):
        assert path == "/api/messenger/send"
        assert body["channel"] == "telegram"
        return {"ok": True, "channel": "telegram"}

    monkeypatch.setattr("quantum_office_mcp.handlers.text_bot_request", fake_tb)
    out = call_tool("telegram.send", {"chat_id": "1", "text": "привет"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is True


def test_messenger_history(monkeypatch):
    def fake_tb(method, path, body=None, query=None, timeout=90.0):
        assert method == "GET"
        assert path == "/api/messenger/history"
        assert query["channel"] == "telegram"
        assert query["user_id"] == "963782"
        return {
            "ok": True,
            "session_id": "telegram:963782",
            "messages": [{"role": "user", "content": "привет"}],
        }

    monkeypatch.setattr("quantum_office_mcp.handlers.text_bot_request", fake_tb)
    out = call_tool("telegram.history", {"user_id": "963782", "limit": 10})
    payload = json.loads(out["content"][0]["text"])
    assert payload["session_id"] == "telegram:963782"


def test_messenger_chats(monkeypatch):
    def fake_tb(method, path, body=None, query=None, timeout=90.0):
        assert path == "/api/messenger/chats"
        assert query["channel"] == "max"
        return {"ok": True, "chats": [{"session_id": "max:1"}]}

    monkeypatch.setattr("quantum_office_mcp.handlers.text_bot_request", fake_tb)
    out = call_tool("messenger.chats", {"channel": "max"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["chats"][0]["session_id"] == "max:1"


def test_kb_search_legacy_first(monkeypatch):
    calls = []

    def fake_knowledge(method, path, body=None, timeout=120.0, use_brain_headers=True):
        calls.append((path, body, timeout))
        if path == "/api/knowledge/query":
            assert body["mode"] == "legacy"
            assert timeout <= 12.0
            return {"ok": True, "text": "СБП выплаты", "topic": "СБП", "http_status": 200}
        if path == "/api/brain/search":
            raise AssertionError("brain must not be called when legacy has text")
        return {"ok": False}

    monkeypatch.setattr("quantum_office_mcp.handlers.knowledge_request", fake_knowledge)
    out = call_tool("kb.search", {"query": "СБП", "limit": 3})
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is True
    assert payload["source"] == "legacy_first"
    assert "СБП" in (payload.get("text") or "")
    assert [p for p, _, _ in calls] == ["/api/knowledge/query"]


def test_html_body_extract():
    from email.message import EmailMessage

    # Import from outreach package path
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "outreach"
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from reply_watcher import _plain_body

    msg = EmailMessage()
    msg["Subject"] = "Re: test"
    msg.set_content(
        "<html><body><p>Интересно, давайте созвонимся</p></body></html>",
        subtype="html",
        charset="utf-8",
    )
    text = _plain_body(msg)
    assert "созвонимся" in text
