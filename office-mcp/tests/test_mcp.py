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
    assert "files.read" in names
    assert "conference.create" in names


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
    def fake_tb(method, path, body=None, timeout=90.0):
        assert path == "/api/messenger/send"
        assert body["channel"] == "telegram"
        return {"ok": True, "channel": "telegram"}

    monkeypatch.setattr("quantum_office_mcp.handlers.text_bot_request", fake_tb)
    out = call_tool("telegram.send", {"chat_id": "1", "text": "привет"})
    payload = json.loads(out["content"][0]["text"])
    assert payload["ok"] is True
