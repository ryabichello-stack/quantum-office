"""send_file forwards business_connection_id to files API."""

from __future__ import annotations

import json

import ava_client as ac


def test_send_file_forwards_business_connection(monkeypatch):
    captured: dict = {}

    def fake_post(url, body, timeout=30.0):
        captured["url"] = url
        captured["body"] = body
        return {"ok": True, "sent": True, "filename": "x.pdf"}

    monkeypatch.setattr(ac, "_post_json", fake_post)
    monkeypatch.setattr(ac, "FILES_BASE", "http://files.test")

    raw = ac.run_tool(
        "send_file",
        {
            "source": "local",
            "path": "quantum_payouts_presentation_small.pdf",
            "via": "telegram",
            "to": "me",
            "caption": "Презентация",
        },
        telegram_chat_id="12345",
        business_connection_id="bc-xyz",
        channel="telegram_business",
        role="guest",
    )
    data = json.loads(raw)
    assert data["ok"] is True
    assert captured["url"].endswith("/api/files/send")
    assert captured["body"]["to"] == "12345"
    assert captured["body"]["business_connection_id"] == "bc-xyz"
    assert captured["body"]["via"] == "telegram"
