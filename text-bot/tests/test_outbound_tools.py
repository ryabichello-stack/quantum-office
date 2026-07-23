"""Outbound console tools: owner gate, phone normalize, confirm, per-call script."""

from __future__ import annotations

import json

import ava_client as ac


def test_normalize_dial_phone():
    assert ac._normalize_dial_phone("+7 (900) 123-45-67") == "79001234567"
    assert ac._normalize_dial_phone("89001234567") == "79001234567"
    assert ac._normalize_dial_phone("9001234567") == "79001234567"


def test_console_headers_include_bearer(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    headers = ac._console_headers()
    assert headers["X-Console-Token"] == "tok"
    assert headers["Authorization"] == "Bearer tok"


def test_outbound_tools_owner_only(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    monkeypatch.setattr(ac, "CONSOLE_BASE", "http://127.0.0.1:8013")
    names = {t["function"]["name"] for t in ac.tools_for_role("owner")}
    assert "outbound_dial" in names
    assert "await_outbound_result" in names
    assert "draft_outbound_call" in names
    guest = {t["function"]["name"] for t in ac.tools_for_role("guest")}
    assert "outbound_dial" not in guest


def test_draft_outbound_call_shows_full_scenario():
    out = json.loads(
        ac.run_tool(
            "draft_outbound_call",
            {
                "phone": "+7 (931) 103-13-71",
                "goal": "зовут Света пригласи на свидание от имени Дениса",
                "callee_name": "Света",
                "on_behalf_of": "Дениса",
            },
            role="owner",
        )
    )
    assert out["ok"] is True
    assert out["phone"] == "79311031371"
    assert "Quantum" not in (out["greeting"] or "")
    assert "Денис" in (out["greeting"] or "")
    assert "Света" in (out["greeting"] or "")
    assert "Greeting:" in out["owner_message"]
    assert "Script:" in out["owner_message"]
    assert "да, звони" in out["owner_message"]


def test_await_outbound_result_matches_phone(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        if path == "/api/calls":
            return {
                "ok": True,
                "calls": [
                    {
                        "call_id": "old.1",
                        "caller_number": "79311031371",
                        "start_time": "2026-07-23T21:38:11Z",
                        "duration_seconds": 22,
                        "outcome": "completed",
                        "transcript_preview": "выплаты",
                    },
                    {
                        "call_id": "new.2",
                        "caller_number": "79311031371",
                        "start_time": "2026-07-23T22:03:24Z",
                        "duration_seconds": 133,
                        "outcome": "completed",
                        "transcript_preview": "субботу",
                    },
                ],
            }
        assert path == "/api/calls/new.2"
        return {
            "ok": True,
            "call": {
                "call_id": "new.2",
                "caller_number": "79311031371",
                "start_time": "2026-07-23T22:03:24Z",
                "duration_seconds": 133,
                "outcome": "completed",
                "conversation": [
                    {"role": "assistant", "content": "суббота в 14:00"},
                    {"role": "user", "content": "устрицы"},
                ],
            },
        }

    monkeypatch.setattr(ac, "_console_request", fake_req)
    monkeypatch.setattr(ac.time, "sleep", lambda *_a, **_k: None)
    out = json.loads(
        ac.run_tool(
            "await_outbound_result",
            {
                "phone": "79311031371",
                "dialed_after": "2026-07-23T22:03:00Z",
                "timeout_sec": 15,
            },
            role="owner",
        )
    )
    assert out["ok"] is True
    assert out["call_id"] == "new.2"
    assert "устрицы" in out["conversation"][1]["content"]
    conv_blob = json.dumps(out.get("conversation") or [], ensure_ascii=False)
    assert "выплаты" not in conv_blob
    assert "суббота" in conv_blob


def test_outbound_dial_requires_confirm(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {"phone": "79001234567", "confirm": False, "goal": "тест"},
            role="owner",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "confirm_required"


def test_outbound_dial_requires_goal_or_script(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {"phone": "79001234567", "confirm": True},
            role="owner",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "goal_or_script_required"


def test_outbound_dial_forbidden_for_guest():
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {"phone": "79001234567", "confirm": True, "goal": "тест"},
            role="guest",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "forbidden"


def test_outbound_dial_calls_console(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    monkeypatch.setattr(ac, "CONSOLE_BASE", "http://127.0.0.1:8013")

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        assert method == "POST"
        assert path == "/api/outbound/dial"
        assert body == {
            "phone": "79001234567",
            "context": "outbound",
            "greeting": "Алло, это Анна",
            "script": "Ты Анна из Acme",
            "use_knowledge": True,
        }
        return {"ok": True, "channel": "PJSIP/79001234567@mango-employee"}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {
                "phone": "8 (900) 123-45-67",
                "confirm": True,
                "goal": "тест",
                "greeting": "Алло, это Анна",
                "script": "Ты Анна из Acme",
                "use_knowledge": True,
            },
            role="owner",
        )
    )
    assert out["ok"] is True
    assert out["phone"] == "79001234567"
    assert out["per_call_override"]["greeting"] is True
    assert out["per_call_override"]["script"] is True


def test_scrub_quantum_labs_from_greeting_when_goal_is_personal():
    greet, script, scrubbed = ac._scrub_outbound_brand_leak(
        goal="От имени Дениса пригласи Свету на свидание",
        greeting=(
            "Здравствуйте, Света! Это ИИ‑секретарь Quantum Labs, "
            "я звоню от имени Дениса. Удобно говорить минуту?"
        ),
        script="Ты ИИ-секретарь Quantum Labs. Пригласи на свидание.",
    )
    assert scrubbed is True
    assert "Quantum" not in (greet or "")
    assert "Дениса" in (greet or "")
    assert "ЗАПРЕТ ИДЕНТИЧНОСТИ" in (script or "")


def test_outbound_dial_scrubs_brand_on_dial(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    captured = {}

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        captured["body"] = body
        return {"ok": True}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {
                "phone": "79311031371",
                "confirm": True,
                "goal": "От имени Дениса пригласи Свету на свидание",
                "greeting": (
                    "Здравствуйте, Света! Это ИИ-секретарь Quantum Labs, "
                    "я звоню от имени Дениса. Удобно минуту?"
                ),
                "script": "Пригласи Свету на свидание от Дениса.",
            },
            role="owner",
        )
    )
    assert out["ok"] is True
    assert "Quantum" not in captured["body"]["greeting"]
    assert "Дениса" in captured["body"]["greeting"]


def test_outbound_dial_synthesizes_script_from_goal(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    captured = {}

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        captured["body"] = body
        return {"ok": True}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {
                "phone": "79311031371",
                "confirm": True,
                "goal": "От имени Дениса пригласи Свету на свидание",
            },
            role="owner",
        )
    )
    assert out["ok"] is True
    body = captured["body"]
    assert body["phone"] == "79311031371"
    assert "пригласи Свету" in body["script"]
    assert "массовые выплаты" in body["script"]  # ban text present
    assert "Quantum Labs" in body["script"]
    assert body["use_knowledge"] is False
    assert out["per_call_override"]["synthesized_from_goal"] is True


def test_outbound_dial_use_default_script_allows_empty(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    captured = {}

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        captured["body"] = body
        return {"ok": True}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(
        ac.run_tool(
            "outbound_dial",
            {"phone": "79001234567", "confirm": True, "use_default_script": True},
            role="owner",
        )
    )
    assert out["ok"] is True
    assert captured["body"] == {"phone": "79001234567", "context": "outbound"}
    assert out["per_call_override"]["use_default_script"] is True


def test_get_outbound_scenario_uses_script_endpoint(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        assert method == "GET"
        assert path == "/api/outbound/script"
        return {"ok": True, "greeting": "Привет", "script": "Ты Гарик" * 200}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(ac.run_tool("get_outbound_scenario", {}, role="owner"))
    assert out["ok"] is True
    assert out["script_chars"] > 0
    assert "script_preview" in out


def test_update_outbound_scenario_isolates_context(monkeypatch):
    monkeypatch.setattr(ac, "CONSOLE_ENABLED", True)
    monkeypatch.setattr(ac, "CONSOLE_TOKEN", "tok")
    calls = []

    def fake_req(method, path, *, body=None, query=None, timeout=30.0):
        calls.append({"method": method, "path": path, "body": body})
        if path == "/api/actions/restart-engine":
            return {"ok": True, "restarted": True}
        return {"ok": True, "greeting": "Привет", "script": "Ты Гарик"}

    monkeypatch.setattr(ac, "_console_request", fake_req)
    out = json.loads(
        ac.run_tool(
            "update_outbound_scenario",
            {"greeting": "Привет", "prompt": "Ты Гарик", "restart_engine": True},
            role="owner",
        )
    )
    assert out["ok"] is True
    assert calls[0]["path"] == "/api/outbound/script"
    assert calls[0]["body"]["greeting"] == "Привет"
    assert calls[0]["body"]["script"] == "Ты Гарик"
    assert "context" not in calls[0]["body"]
    assert calls[1]["path"] == "/api/actions/restart-engine"
    assert out["restart_engine"]["ok"] is True
